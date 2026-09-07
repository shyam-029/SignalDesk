# Phase 7 tests — job-run recording (durable job status).
#
# The recorder (jobs._record_pass) redirects SessionLocal at the TEST database
# via monkeypatch, exactly like the existing ingestion tests. No scheduler,
# no providers, no network.

from app import jobs as jobs_module
from app.models import JobRun, Stock, Universe, stock_universe
from app.providers.base import MarketDataError
from sqlalchemy import insert, select


async def _seed_universe(session_factory) -> None:
    async with session_factory() as session:
        session.add(Universe(name=jobs_module.UNIVERSE_NAME))
        session.add(Stock(symbol="AAA.NS", name="AAA", sector="IT"))
        await session.flush()
        stock = await session.scalar(select(Stock).where(Stock.symbol == "AAA.NS"))
        uni = await session.scalar(
            select(Universe).where(Universe.name == jobs_module.UNIVERSE_NAME)
        )
        await session.execute(
            insert(stock_universe).values(universe_id=uni.id, stock_id=stock.id)
        )
        await session.commit()


async def _runs(session_factory, job_name: str) -> list[JobRun]:
    async with session_factory() as session:
        return list(
            (await session.execute(
                select(JobRun).where(JobRun.job_name == job_name)
            )).scalars()
        )


async def test_record_pass_success(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    async def ok_pass():
        return {"fetched": 3, "errors": 0}

    await jobs_module._record_pass("ok_job", ok_pass)

    [run] = await _runs(session_factory, "ok_job")
    assert run.status == "success"
    assert run.items_processed == 3
    assert run.items_failed == 0
    assert run.started_at is not None
    assert run.finished_at is not None
    assert run.duration_ms is not None and run.duration_ms >= 0
    assert run.error_summary is None


async def test_record_pass_failure(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    async def boom():
        raise RuntimeError("database exploded")

    # A failing pass is recorded AND swallowed (run_nightly isolation).
    await jobs_module._record_pass("boom_job", boom)

    [run] = await _runs(session_factory, "boom_job")
    assert run.status == "failed"
    assert run.error_summary is not None
    assert "database exploded" in run.error_summary
    assert run.duration_ms is not None


async def test_record_pass_partial(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    async def partial_pass():
        return {"fetched": 240, "errors": 8}

    await jobs_module._record_pass("partial_job", partial_pass)

    [run] = await _runs(session_factory, "partial_job")
    assert run.status == "partial"
    assert run.items_processed == 240
    assert run.items_failed == 8
    assert "8" in (run.error_summary or "")


async def test_error_summary_is_truncated(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    async def long_error():
        raise RuntimeError("x" * (jobs_module.ERROR_SUMMARY_MAX * 4))

    await jobs_module._record_pass("long_err", long_error)

    [run] = await _runs(session_factory, "long_err")
    assert len(run.error_summary) <= jobs_module.ERROR_SUMMARY_MAX


async def test_passes_are_isolated(session_factory, monkeypatch):
    """A failing pass does not stop the following passes."""
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    calls = []

    async def first():
        raise MarketDataError("provider down")

    async def second():
        calls.append("second")
        return {"fetched": 1, "errors": 0}

    await jobs_module._record_pass("p1", first)
    await jobs_module._record_pass("p2", second)

    assert calls == ["second"]


async def test_record_pass_survives_status_db_failure(session_factory, monkeypatch):
    """If job_runs writes fail, the pass still runs (recording is best-effort)."""
    class BrokenFactory:
        def __call__(self):
            raise OSError("db gone")

    monkeypatch.setattr(jobs_module, "SessionLocal", BrokenFactory())
    ran = []

    async def ok_pass():
        ran.append(True)
        return {"fetched": 1, "errors": 0}

    await jobs_module._record_pass("no_status_db", ok_pass)
    assert ran == [True]


async def test_ingest_universe_records_run_via_nightly(session_factory, monkeypatch):
    """End-to-end: nightly wrapper records one row per pass."""
    await _seed_universe(session_factory)
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    # Providers stubbed: no network.
    class P:
        name = "fake"

        async def get_price_history(self, symbol, period):
            return []

        async def get_fundamentals(self, symbol):
            raise MarketDataError("no data")

        async def get_financial_history(self, symbol, period_type="annual"):
            return []

        async def get_company_profile(self, symbol):
            raise MarketDataError("no profile")

    provider = P()
    await jobs_module._record_pass(
        "ingest_prices", jobs_module.ingest_universe, provider
    )
    [run] = await _runs(session_factory, "ingest_prices")
    assert run.status in ("success", "partial")
    assert run.items_processed is not None


async def test_latest_runs_and_last_success(session_factory, monkeypatch):
    """Repository helpers used by /debug/jobs and /status."""
    from datetime import datetime, timezone

    from app.repositories import job_runs as repo

    async with session_factory() as session:
        session.add_all(
            [
                JobRun(
                    job_name="ingest_prices", status="success",
                    started_at=datetime(2026, 9, 6, 18, 30, tzinfo=timezone.utc),
                    finished_at=datetime(2026, 9, 6, 18, 50, tzinfo=timezone.utc),
                ),
                JobRun(
                    job_name="ingest_prices", status="failed",
                    started_at=datetime(2026, 9, 7, 18, 30, tzinfo=timezone.utc),
                    finished_at=datetime(2026, 9, 7, 18, 31, tzinfo=timezone.utc),
                    error_summary="MarketDataError: x",
                ),
            ]
        )
        await session.commit()

    async with session_factory() as session:
        latest = await repo.latest_runs(session)
        assert latest["ingest_prices"].status == "failed"
        last_ok = await repo.last_successful_run(session, job_name="ingest_prices")
        assert last_ok is not None and last_ok.status == "success"
        # Stale detection used by /status.
        from app.main import INGESTION_STALE_AFTER_SECONDS

        age = (
            datetime.now(timezone.utc) - last_ok.finished_at
        ).total_seconds()
        assert age < INGESTION_STALE_AFTER_SECONDS
