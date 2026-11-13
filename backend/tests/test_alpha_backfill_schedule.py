# Tiered nightly schedule (work list item 29): the weekly full alpha-history
# recompute and the slow statement passes run on an interval read from their
# own last successful run; stocks without history are filled every night.

from datetime import date, datetime, timedelta, timezone

from app import jobs
from app.models import AlphaScore, JobRun

NOW = datetime(2026, 11, 16, 10, 45, tzinfo=timezone.utc)


async def _ran(session_factory, name: str, when: datetime, status: str = "success"):
    async with session_factory() as session:
        session.add(JobRun(job_name=name, status=status, started_at=when, finished_at=when))
        await session.commit()


async def test_pass_due_follows_its_last_successful_run(session_factory, monkeypatch):
    monkeypatch.setattr(jobs, "SessionLocal", session_factory)
    name = "ingest_company_profiles"
    assert await jobs._pass_due(name, 7, NOW) is True  # never ran
    await _ran(session_factory, name, NOW - timedelta(days=3))
    assert await jobs._pass_due(name, 7, NOW) is False
    assert await jobs._pass_due(name, 3, NOW) is True
    # A run that starts a few hours earlier in the day than last week's is
    # still due (12 h of slack), but not a day early.
    await _ran(session_factory, "weekly.x", NOW - timedelta(days=6, hours=20))
    assert await jobs._pass_due("weekly.x", 7, NOW) is True
    assert await jobs._pass_due("weekly.x", 7, NOW - timedelta(days=1)) is False


async def test_pass_due_ignores_failed_runs(session_factory, monkeypatch):
    monkeypatch.setattr(jobs, "SessionLocal", session_factory)
    await _ran(session_factory, "ingest_balance_sheets", NOW - timedelta(days=1), "failed")
    assert await jobs._pass_due("ingest_balance_sheets", 7, NOW) is True


async def test_full_alpha_recompute_is_weekly_and_can_be_forced(session_factory, monkeypatch):
    monkeypatch.setattr(jobs, "SessionLocal", session_factory)
    monkeypatch.delenv("ALPHA_BACKFILL_FULL", raising=False)
    monkeypatch.delenv("INGEST_ALL_PASSES", raising=False)
    assert await jobs._alpha_full_backfill_due(NOW) is True
    await _ran(session_factory, jobs.ALPHA_FULL_JOB, NOW - timedelta(days=2))
    assert await jobs._alpha_full_backfill_due(NOW) is False
    monkeypatch.setenv("ALPHA_BACKFILL_FULL", "1")
    assert await jobs._alpha_full_backfill_due(NOW) is True
    monkeypatch.delenv("ALPHA_BACKFILL_FULL")
    monkeypatch.setenv("INGEST_ALL_PASSES", "true")
    assert await jobs._alpha_full_backfill_due(NOW) is True


def test_results_season_windows():
    inside = [date(2026, 1, 10), date(2026, 2, 20), date(2026, 4, 30), date(2026, 5, 31),
              date(2026, 7, 15), date(2026, 8, 1), date(2026, 10, 10), date(2026, 11, 20)]
    outside = [date(2026, 1, 9), date(2026, 2, 21), date(2026, 3, 15), date(2026, 6, 1),
               date(2026, 9, 30), date(2026, 11, 21), date(2026, 12, 25)]
    assert all(jobs.in_results_season(d) for d in inside)
    assert not any(jobs.in_results_season(d) for d in outside)


async def test_nightly_skips_slow_passes_that_are_not_due(session_factory, monkeypatch):
    monkeypatch.setattr(jobs, "SessionLocal", session_factory)
    monkeypatch.delenv("INGEST_ALL_PASSES", raising=False)
    monkeypatch.delenv("ALPHA_BACKFILL_FULL", raising=False)
    recent = datetime.now(timezone.utc) - timedelta(hours=2)
    for name in ("ingest_financial_periods", "ingest_balance_sheets",
                 "ingest_company_profiles", jobs.ALPHA_FULL_JOB):
        await _ran(session_factory, name, recent)
    ran: list[str] = []

    async def fake_record(name, run, *a, **k):
        ran.append(name)
        return "success"

    monkeypatch.setattr(jobs, "_record_pass", fake_record)
    await jobs._ingest_passes()
    assert "ingest_prices" in ran and "ingest_financials" in ran
    assert "backfill_alpha_history" in ran and jobs.ALPHA_FULL_JOB not in ran
    for name in ("ingest_financial_periods", "ingest_balance_sheets", "ingest_company_profiles"):
        assert name not in ran

    ran.clear()
    monkeypatch.setenv("INGEST_ALL_PASSES", "1")
    await jobs._ingest_passes()
    for name in ("ingest_financial_periods", "ingest_balance_sheets",
                 "ingest_company_profiles", jobs.ALPHA_FULL_JOB):
        assert name in ran


async def _seed_snapshots(session_factory, counts: dict[str, int]) -> None:
    async with session_factory() as session:
        start = date(2024, 1, 1)
        for symbol, n in counts.items():
            for i in range(n):
                session.add(AlphaScore(symbol=symbol, date=start + timedelta(days=i),
                                       technical=50, composite=50))
        await session.commit()


async def test_missing_history_selects_new_and_thin_stocks(session_factory):
    await _seed_snapshots(session_factory, {"FULL.NS": 150, "THIN.NS": 3})
    async with session_factory() as session:
        got = await jobs._symbols_missing_alpha_history(
            session, ["FULL.NS", "THIN.NS", "NEW.NS"]
        )
    assert got == ["THIN.NS", "NEW.NS"]


async def test_weekday_pass_backfills_only_missing(session_factory, monkeypatch):
    await _seed_snapshots(session_factory, {"FULL.NS": 150})
    done: list[str] = []

    async def fake_universe(_session):
        return ["FULL.NS", "NEW.NS"]

    async def fake_one(symbol, _written):
        done.append(symbol)
        return 1

    monkeypatch.setattr(jobs, "SessionLocal", session_factory)
    monkeypatch.setattr(jobs, "_get_universe_symbols", fake_universe)
    monkeypatch.setattr(jobs, "_backfill_one_alpha", fake_one)

    out = await jobs.backfill_alpha_history(full=False)
    assert done == ["NEW.NS"] and out["full"] is False and out["symbols"] == 1

    done.clear()
    out = await jobs.backfill_alpha_history(full=True)
    assert sorted(done) == ["FULL.NS", "NEW.NS"] and out["full"] is True
