# The Phase 1 read-only SQL scripts run against the CI test database so a
# syntax error or a renamed column can never first surface in production.
#
# Strategy: execute each script on a raw asyncpg connection (multi-statement
# scripts need the simple query protocol, which SQLAlchemy's driver-SQL path
# does not allow), then prove it changed nothing and is structurally read-only.

import re
from pathlib import Path

import pytest
from sqlalchemy import text

OPS_SQL = Path(__file__).resolve().parents[2] / "ops" / "sql"
SCRIPTS = ["storage_forensics.sql", "job_health.sql"]

_WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|VACUUM|REINDEX)\b",
    re.IGNORECASE,
)


def _strip_sql_noise(sql: str) -> str:
    """Remove -- comments and quoted/dollar-quoted text for keyword scanning."""
    no_comments = re.sub(r"--[^\n]*", "", sql)
    no_dollar = re.sub(r"\$\$.*?\$\$", "", no_comments, flags=re.DOTALL)
    return re.sub(r"'(?:[^']|'')*'", "''", no_dollar)


@pytest.mark.parametrize("name", SCRIPTS)
def test_script_is_declared_read_only(name):
    sql = (OPS_SQL / name).read_text(encoding="utf-8")
    code = _strip_sql_noise(sql)
    assert re.search(r"^\s*BEGIN READ ONLY;", code, re.MULTILINE | re.IGNORECASE)
    assert re.search(r"^\s*COMMIT;", code, re.MULTILINE | re.IGNORECASE)
    assert not _WRITE_KEYWORDS.search(code), "ops SQL must contain no write/DDL keyword"


@pytest.mark.parametrize("name", SCRIPTS)
async def test_script_runs_on_empty_schema_and_changes_nothing(name, engine, session_factory):
    sql = (OPS_SQL / name).read_text(encoding="utf-8")

    async with engine.connect() as conn:
        before = (await conn.execute(text("SELECT count(*) FROM stocks"))).scalar_one()
        raw = await conn.get_raw_connection()
        await raw.driver_connection.execute(sql)
        await conn.rollback()

    async with engine.connect() as conn:
        after = (await conn.execute(text("SELECT count(*) FROM stocks"))).scalar_one()
    assert before == after == 0


# --- Seeded run + read-only proof (fresh connections) ----------------------
#
# The empty-schema run above executes inside SQLAlchemy's already-open
# transaction, where the script's own BEGIN READ ONLY is ignored (Postgres
# only warns). The tests below use a fresh asyncpg connection so the script
# runs exactly as psql sends it in production: its own READ ONLY transaction,
# over real rows, so the GROUP BY / FILTER / percentile paths are exercised.

RAW_DSN = "postgresql://postgres:postgres@localhost:5432/signaldesk_test"


async def test_storage_forensics_runs_over_seeded_rows(seeded, session_factory):
    import asyncpg
    from datetime import date, datetime, timedelta, timezone

    from app.models import AlphaScore, JobRun, NewsArticle

    async with session_factory() as session:
        today = date.today()
        session.add_all(
            [
                AlphaScore(symbol="RELIANCE.NS", date=today, composite=60,
                           technical=55, components_json={"trend": 1}),
                AlphaScore(symbol="RELIANCE.NS", date=today - timedelta(days=1),
                           composite=58, fundamental=70, technical=50,
                           components_json={}),
                # Symbol absent from the catalog: the orphan check must count it.
                AlphaScore(symbol="GONE.NS", date=today, composite=40,
                           technical=40, components_json=None),
                NewsArticle(symbol="TCS.NS", source="rss", title="t",
                            url="https://example.invalid/a",
                            published_at=datetime.now(timezone.utc),
                            content="body"),
                JobRun(job_name="ingest_prices", status="success",
                       started_at=datetime.now(timezone.utc)),
            ]
        )
        await session.commit()

    conn = await asyncpg.connect(RAW_DSN)
    try:
        notices: list[str] = []
        conn.add_log_listener(lambda _c, msg: notices.append(msg.message))
        await conn.execute((OPS_SQL / "storage_forensics.sql").read_text(encoding="utf-8"))
        # The guarded DO block reports on the optional tooling either way.
        assert any(n.startswith("neon_cluster_size") for n in notices)
        assert any(n.startswith("pgstattuple_approx") for n in notices)
        # The script left no transaction open and wrote nothing.
        assert await conn.fetchval("SELECT count(*) FROM alpha_scores") == 3
    finally:
        await conn.close()


async def test_read_only_wrapper_rejects_writes(session_factory):
    import asyncpg

    conn = await asyncpg.connect(RAW_DSN)
    try:
        with pytest.raises(asyncpg.exceptions.ReadOnlySQLTransactionError):
            await conn.execute(
                "BEGIN READ ONLY; "
                "INSERT INTO universes (name) VALUES ('should_never_exist'); "
                "COMMIT;"
            )
    finally:
        await conn.close()
