# Storage guardrails tests (M2-T1). Zero-network: the canary math is pure,
# and the retention pass runs against signaldesk_test via the monkeypatched
# SessionLocal pattern (same as test_statements_funds.py).
#
# The canary test is a CI-visible alarm: it pins the measured production
# constants (2026-09-09 db-probe: 383 MB used, ~0.6-1 MB/day growth) and
# asserts the worst-case 90-day projection stays under the 512 MB Neon cap.
# When a probe refresh of the baseline pushes the projection past the cap,
# this test goes red and the gated retention cut becomes due.

from datetime import date, timedelta

from sqlalchemy import func, select

from app import jobs as jobs_module
from app.config import settings
from app.models import AlphaScore, Stock
from app.services import storage as storage_svc


# --- Canary + gate math (pure) ------------------------------------------------


def test_cut_gate_boundary():
    """Fires at exactly the threshold; never below it."""
    mb = storage_svc.BYTES_PER_MB
    assert storage_svc.cut_gate_fires(450 * mb) is True       # exactly at
    assert storage_svc.cut_gate_fires(450 * mb - 1) is False  # just below
    assert storage_svc.cut_gate_fires(383 * mb) is False      # current baseline
    assert storage_svc.cut_gate_fires(512 * mb) is True
    # An explicit override moves the gate.
    assert storage_svc.cut_gate_fires(100 * mb, threshold_mb=100) is True
    assert storage_svc.cut_gate_fires(100 * mb, threshold_mb=101) is False


def test_projection_math():
    mb = storage_svc.BYTES_PER_MB
    assert storage_svc.project_bytes(383 * mb, 1 * mb, 30) == 413 * mb
    assert storage_svc.headroom_bytes(383 * mb) == (512 - 383) * mb


def test_canary_worst_case_stays_under_cap():
    """THE canary: worst-case 90-day projection from the pinned baseline.

    383 MB + 1 MB/day * 90 = 473 MB < 512 MB cap. If this goes red, a
    baseline/growth refresh has crossed the cap: run the gated cut.
    """
    verdict = storage_svc.canary_verdict()
    assert verdict["ok"] is True
    assert verdict["cut_fires_at_baseline"] is False
    assert verdict["projections_worst_case_mb"]["day_90"] < 512.0
    # Arithmetic is exactly the documented model: baseline + high-band rate.
    assert verdict["projections_worst_case_mb"]["day_30"] == 413.0
    assert verdict["projections_worst_case_mb"]["day_90"] == 473.0


def test_canary_alarms_when_baseline_crosses_cap():
    """A synthetic baseline near the cap flips the verdict red."""
    verdict = storage_svc.canary_verdict(used_bytes=505 * storage_svc.BYTES_PER_MB)
    assert verdict["ok"] is False
    assert verdict["cut_fires_at_baseline"] is True


def test_settings_pin_defaults():
    """Pin the M2-T1 contract: gated cut at 450 MB, M2 passes flag OFF.

    enable_m2_passes=False is the T7-week protection guarantee (M2 plan
    section 17): nothing scheduled reads it yet, and it must default OFF
    until the owner flips it after the one-week cron baseline clears.
    """
    assert settings.storage_cut_threshold_mb == 450
    assert settings.storage_cut_keep_top == 250
    assert settings.storage_cut_depth_days == 366
    assert settings.enable_m2_passes is False


# --- Retention pass (DB, signaldesk_test) -------------------------------------


async def _seed_alpha_history(session_factory) -> None:
    """Two keep-set stocks (top-250 by rank) + two prune-set stocks, each
    with one old (< 1y cutoff) and one recent alpha snapshot."""
    old = date.today() - timedelta(days=400)   # older than the 366d cutoff
    recent = date.today() - timedelta(days=100)
    async with session_factory() as session:
        session.add_all(
            [
                Stock(symbol="TOP1.NS", name="Top 1", mcap_rank=1),
                Stock(symbol="TOP250.NS", name="Top 250", mcap_rank=250),
                Stock(symbol="OUT251.NS", name="Ranked out 251", mcap_rank=251),
                Stock(symbol="NULLRANK.NS", name="Unranked", mcap_rank=None),
            ]
        )
        await session.flush()
        for symbol, _ in (
            ("TOP1.NS", 1), ("TOP250.NS", 250),
            ("OUT251.NS", 251), ("NULLRANK.NS", None),
        ):
            session.add_all(
                [
                    AlphaScore(symbol=symbol, date=old, composite=50),
                    AlphaScore(symbol=symbol, date=recent, composite=60),
                ]
            )
        await session.commit()


async def test_prune_inert_at_current_storage(session_factory, monkeypatch):
    """THE inertness proof: at a real (small) database size below the 450 MB
    threshold the pass deletes NOTHING and reports fired=False."""
    await _seed_alpha_history(session_factory)
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    result = await jobs_module.prune_alpha_history_outside_top250()

    assert result["fired"] is False
    assert result["deleted"] == 0
    async with session_factory() as session:
        n = await session.scalar(select(func.count(AlphaScore.id)))
        assert n == 8  # nothing touched


async def test_prune_fires_when_threshold_met(session_factory, monkeypatch):
    """With the gate forced (threshold 0 MB), old rows outside the top-250
    keep-set are deleted; keep-set rows and recent rows survive."""
    await _seed_alpha_history(session_factory)
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    result = await jobs_module.prune_alpha_history_outside_top250(threshold_mb=0)

    assert result["fired"] is True
    assert result["deleted"] == 2  # OUT251 + NULLRANK old rows only
    assert result["keep_top"] == 250
    async with session_factory() as session:
        pairs = set(
            (symbol, row_date)
            for symbol, row_date in (
                await session.execute(select(AlphaScore.symbol, AlphaScore.date))
            ).all()
        )
    today = date.today()
    # Keep-set: both rows survive at full depth.
    assert ("TOP1.NS", today - timedelta(days=400)) in pairs
    assert ("TOP250.NS", today - timedelta(days=400)) in pairs
    # Prune-set: old rows gone, recent rows kept.
    assert ("OUT251.NS", today - timedelta(days=400)) not in pairs
    assert ("NULLRANK.NS", today - timedelta(days=400)) not in pairs
    assert ("OUT251.NS", today - timedelta(days=100)) in pairs
    assert ("NULLRANK.NS", today - timedelta(days=100)) in pairs
    assert {s for s, _ in pairs} == {"TOP1.NS", "TOP250.NS", "OUT251.NS", "NULLRANK.NS"}


async def test_prune_idempotent(session_factory, monkeypatch):
    await _seed_alpha_history(session_factory)
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    r1 = await jobs_module.prune_alpha_history_outside_top250(threshold_mb=0)
    r2 = await jobs_module.prune_alpha_history_outside_top250(threshold_mb=0)

    assert (r1["deleted"], r2["deleted"]) == (2, 0)
    async with session_factory() as session:
        n = await session.scalar(select(func.count(AlphaScore.id)))
        assert n == 6


async def test_prune_respects_settings_depth(session_factory, monkeypatch):
    """The depth comes from settings.storage_cut_depth_days (366 default):
    a row at exactly cutoff-1 survives, a row past it does not."""
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    cutoff = date.today() - timedelta(days=settings.storage_cut_depth_days)
    async with session_factory() as session:
        session.add(Stock(symbol="OUT.NS", name="Out", mcap_rank=999))
        await session.flush()
        session.add_all(
            [
                AlphaScore(symbol="OUT.NS", date=cutoff - timedelta(days=1), composite=1),
                AlphaScore(symbol="OUT.NS", date=cutoff, composite=2),
                AlphaScore(symbol="OUT.NS", date=cutoff + timedelta(days=1), composite=3),
            ]
        )
        await session.commit()

    result = await jobs_module.prune_alpha_history_outside_top250(threshold_mb=0)

    assert result["deleted"] == 1
    assert result["cutoff"] == cutoff.isoformat()
    async with session_factory() as session:
        remaining = set(await session.scalars(select(AlphaScore.date)))
    assert remaining == {cutoff, cutoff + timedelta(days=1)}
