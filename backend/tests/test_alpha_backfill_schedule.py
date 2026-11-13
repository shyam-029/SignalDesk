# Weekly full alpha-history recompute, nightly fill for stocks without
# history (2026-11-13, Neon network-transfer budget).

from datetime import date, timedelta

from app import jobs
from app.models import AlphaScore


def test_full_backfill_runs_on_sundays_only(monkeypatch):
    monkeypatch.delenv("ALPHA_BACKFILL_FULL", raising=False)
    sunday = date(2026, 11, 15)
    assert sunday.weekday() == 6
    assert jobs._alpha_full_backfill_due(sunday) is True
    for d in range(1, 7):
        assert jobs._alpha_full_backfill_due(sunday + timedelta(days=d)) is False


def test_full_backfill_can_be_forced(monkeypatch):
    monkeypatch.setenv("ALPHA_BACKFILL_FULL", "1")
    assert jobs._alpha_full_backfill_due(date(2026, 11, 13)) is True


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

    async def fake_one(symbol, _written, _strength=None):
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
