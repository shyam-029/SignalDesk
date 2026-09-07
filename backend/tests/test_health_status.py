# Phase 7 tests — /health (liveness) vs /status (readiness).
#
# Phase 8: /status is the minimal PUBLIC response (liveness-equivalent,
# {"status": "ok"}); the full readiness detail (db/scheduler/ingestion/
# llm_configured) moved to /status/full behind OPS_API_KEY. These tests
# cover both: public minimal in all modes, full detail with the key.

from datetime import datetime, timedelta, timezone

from app.config import settings
from app.models import JobRun


async def _add_run(session_factory, **kwargs) -> None:
    async with session_factory() as session:
        session.add(JobRun(**kwargs))
        await session.commit()


async def test_health_is_pure_liveness(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def _full(client, headers=None):
    return await client.get("/status/full", headers=headers)


async def test_status_is_public_minimal(client):
    r = await client.get("/status")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_status_full_open_in_dev_without_key(client, session_factory):
    await _add_run(
        session_factory,
        job_name="ingest_prices", status="success",
        started_at=datetime.now(timezone.utc) - timedelta(hours=5),
        finished_at=datetime.now(timezone.utc) - timedelta(hours=5),
    )
    r = await _full(client)
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "up"
    assert body["ingestion"]["stale"] is False
    assert body["ingestion"]["last_success_at"] is not None
    assert body["scheduler"] == "stopped"  # no lifespan in tests
    assert body["status"] == "degraded"  # scheduler stopped -> degraded
    assert isinstance(body["llm_configured"], bool)


async def test_status_flags_stale_ingestion(client, session_factory):
    old = datetime.now(timezone.utc) - timedelta(hours=72)  # beyond 48h TTL
    await _add_run(
        session_factory,
        job_name="ingest_prices", status="success",
        started_at=old, finished_at=old,
    )
    r = await _full(client)
    body = r.json()
    assert body["ingestion"]["stale"] is True
    assert body["status"] == "degraded"


async def test_status_failed_run_does_not_count_as_success(client, session_factory):
    now = datetime.now(timezone.utc)
    await _add_run(
        session_factory,
        job_name="ingest_prices", status="failed",
        started_at=now - timedelta(hours=1), finished_at=now - timedelta(hours=1),
        error_summary="boom",
    )
    r = await _full(client)
    body = r.json()
    assert body["ingestion"]["last_success_at"] is None
    assert body["ingestion"]["stale"] is None  # never ran: unknown, not "stale"


async def test_status_contains_no_secrets(client, session_factory):
    await _add_run(
        session_factory,
        job_name="ingest_prices", status="success",
        started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
    )
    text = (await _full(client)).text
    for forbidden in ("api_key", "token", "password", "database_url", "Authorization"):
        assert forbidden not in text
    if settings.llm_api_key:
        assert settings.llm_api_key not in text
    if settings.upstox_analytics_token:
        assert settings.upstox_analytics_token not in text
