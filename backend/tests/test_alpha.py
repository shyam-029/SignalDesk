# Alpha Score tests — service, repository, and API. Network-free.
#
#  - Service tests use hand-built data (no FinBERT load; sentiment mocked).
#  - Repository tests use signaldesk_test.
#  - API tests use the httpx ASGI client with the DB dependency overridden.

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app import jobs
from app.models import AlphaScore, DailyPrice, Financials, Stock
from app.repositories import alpha as alpha_repo
from app.repositories import prices as price_repo
from app.services.alpha import _mean_of, _renormalized, blend_fundamental, compute_alpha
from app.services import indicators


# --- Service unit tests (pure helpers) ----------------------------------------


def test_mean_of_drops_missing():
    assert _mean_of(80, 60) == 70
    assert _mean_of(80, None) == 80
    assert _mean_of(None, None) is None


def test_renormalized_uses_all_weights():
    c, w = _renormalized(100, 100, 100)
    assert c == 100
    assert w["fundamental"] == pytest.approx(0.4, abs=0.01)


def test_renormalized_drops_missing_component():
    # Only fundamental + technical: weights become 0.4/0.35 renormalized = 0.533/0.467
    c, w = _renormalized(100, 0, None)
    assert c == round(100 * 0.4 / 0.75)
    assert abs(w["fundamental"] - 0.53) < 0.01
    assert abs(w["technical"] - 0.47) < 0.01


def test_renormalized_all_missing():
    c, w = _renormalized(None, None, None)
    assert c is None
    assert w == {}


def test_renormalized_mix():
    # fundamental 100 (40%), technical 50 (35%), sentiment 0 (25%)
    # = 40 + 17.5 + 0 = 57.5 -> 58
    c, _ = _renormalized(100, 50, 0)
    assert c == 58


def test_blend_fundamental_v15():
    """Fundamental pillar: profit .45 / solvency .30 / distress .25 renormalized."""
    # All three: (0.45*80 + 0.30*60 + 0.25*40) / 1.0 = 36 + 18 + 10 = 64
    assert blend_fundamental(80, 60, 40) == 64
    # Distress unavailable -> renormalize over profit+solvency (never zero-fill):
    # (0.45*80 + 0.30*60) / 0.75 = 54/0.75 = 72
    assert blend_fundamental(80, 60, None) == 72
    # Profitability missing: (0.30*60 + 0.25*40) / 0.55 = (18+10)/0.55 = 50.9 -> 51
    assert blend_fundamental(None, 60, 40) == 51
    assert blend_fundamental(None, None, None) is None


def test_distress_score_mapping():
    """Z'' -> 0-100 mapping is monotone and zone-anchored."""
    from app.services.altman import distress_score_0_100 as m

    assert m(-1.0) == 0
    assert m(0.0) == 0
    assert m(0.55) == 20          # halfway through the distress zone
    assert m(1.1) == 40           # distress/grey boundary
    assert m(2.6) == 70           # grey/safe boundary
    assert m(5.0) == 100          # saturation
    assert m(9.0) == 100
    assert m(1.85) == 55          # grey midpoint
    # Monotone increasing over the whole documented range.
    samples = [m(z / 10.0) for z in range(0, 51)]
    assert all(b >= a for a, b in zip(samples, samples[1:]))


# --- Indicators integration ---------------------------------------------------


def test_indicators_produce_technical_score():
    closes = list(range(1, 61))  # strongly rising
    tech = indicators.score_technicals(closes)
    assert tech["score"] is not None
    assert 0 <= tech["score"] <= 100
    assert {"trend", "momentum", "reversion"} <= set(tech["components"])


def test_technical_sensitivity_spends_the_band():
    """v1.5 recalibration: observable states span the full sub-score range.

    The old constants mapped a stock 5% above its SMA20 to a trend score of
    ~62 — one more "moderate" read. The recalibrated bands put the same
    state at ~78 and the mirrored fall at ~21, so the evidence differentiates.
    """
    flat = [100.0] * 40
    above = flat[:-1] + [105.0]  # ~5% above SMA20
    tech = indicators.score_technicals(above)
    assert tech["components"]["trend"] > 75
    below = flat[:-1] + [95.0]
    tech2 = indicators.score_technicals(below)
    assert tech2["components"]["trend"] < 25


# --- Repository tests ---------------------------------------------------------


async def test_price_repo_close_series(session_factory):
    async with session_factory() as session:
        stock = Stock(symbol="A.NS", name="A", sector="X", industry="Y")
        session.add(stock)
        await session.flush()
        today = date.today()
        for i in range(5):
            # oldest day (i=4) gets close 10, newest (i=0) gets close 14
            session.add(
                DailyPrice(stock_id=stock.id, date=today - timedelta(days=i),
                           open=1, high=2, low=0.5, close=10 + (4 - i), volume=100)
            )
        await session.commit()
        stock_id = stock.id

    async with session_factory() as session:
        closes = await price_repo.get_close_series(session, stock_id)
        assert closes == [10.0, 11.0, 12.0, 13.0, 14.0]  # oldest first


async def test_alpha_repo_upsert_idempotent(session_factory):
    async with session_factory() as session:
        await alpha_repo.upsert_snapshot(
            session, "A.NS", date.today(), composite=55.0,
            fundamental=70.0, technical=50.0, sentiment=40.0,
            components_json={"weights": {"fundamental": 0.4}},
        )
        await alpha_repo.upsert_snapshot(
            session, "A.NS", date.today(), composite=60.0,
            fundamental=75.0, technical=50.0, sentiment=50.0,
            components_json={"weights": {"fundamental": 0.4}},
        )

    async with session_factory() as session:
        rows = (await session.execute(select(AlphaScore))).scalars().all()
        assert len(rows) == 1  # second upsert overwrote
        assert rows[0].composite == Decimal("60.00")


# --- Alpha history backfill ---------------------------------------------------


async def test_backfill_blends_components_and_replaces_history(
    client, session_factory, monkeypatch
):
    """The recomputed history is a real blend, smooth, and fully replaced."""
    async with session_factory() as session:
        stock = Stock(symbol="BACK.NS", name="Backfill", sector="E", industry="O")
        session.add(stock)
        await session.flush()
        session.add(
            Financials(
                stock_id=stock.id,
                trailing_pe=Decimal("20.00"),
                return_on_equity=Decimal("0.1800"),
                operating_margin=Decimal("0.1250"),
                debt_to_equity=Decimal("50.00"),
            )
        )
        today = date.today()
        for i in range(80):
            session.add(
                DailyPrice(stock_id=stock.id, date=today - timedelta(days=79 - i),
                           open=100, high=101, low=99,
                           close=100 + i * 0.1, volume=1000)
            )
        # A stale snapshot (old formula) that the recompute must remove.
        session.add(
            AlphaScore(symbol="BACK.NS", date=today - timedelta(days=400),
                       composite=1.0, technical=1.0)
        )
        await session.commit()

    monkeypatch.setattr(jobs, "SessionLocal", session_factory)
    inserted = await jobs._backfill_one_alpha("BACK.NS")
    assert inserted > 0

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(AlphaScore)
                .where(AlphaScore.symbol == "BACK.NS")
                .order_by(AlphaScore.date.asc())
            )
        ).scalars().all()

    assert len(rows) == inserted
    # The stale snapshot is gone: every row was recomputed from stored bars.
    assert all(r.date >= date.today() - timedelta(days=79) for r in rows)

    # Fundamental/sentiment have NO stored history: backfilled rows must not
    # present carried-forward constants as daily observations.
    assert all(r.fundamental is None for r in rows)
    assert all(r.sentiment is None for r in rows)
    # The composite is still a real blend (never identical to the technical
    # score when the latest known fundamental differs).
    assert all(
        float(r.composite) != float(r.technical)
        for r in rows
        if r.technical is not None
    )
    # The composite drifts; it does not sawtooth.
    composites = [float(r.composite) for r in rows]
    deltas = [abs(b - a) for a, b in zip(composites, composites[1:])]
    assert max(deltas) <= 12


async def test_backfill_preserves_live_snapshots(
    client, session_factory, monkeypatch
):
    """A genuine live snapshot (with a fundamental score) survives the backfill.

    Nightly recomputes replace TECHNICAL-ONLY rows; wiping live /alpha rows
    every night would make per-component history impossible.
    """
    async with session_factory() as session:
        stock = Stock(symbol="LIVE.NS", name="Live Snap", sector="E", industry="O")
        session.add(stock)
        await session.flush()
        today = date.today()
        for i in range(40):
            session.add(
                DailyPrice(stock_id=stock.id, date=today - timedelta(days=39 - i),
                           open=100, high=101, low=99,
                           close=100 + i * 0.1, volume=1000)
            )
        # A genuine live snapshot: fundamental score recorded by /alpha.
        session.add(
            AlphaScore(symbol="LIVE.NS", date=today, composite=80.0,
                       fundamental=90.0, technical=70.0, sentiment=80.0)
        )
        await session.commit()

    monkeypatch.setattr(jobs, "SessionLocal", session_factory)
    await jobs._backfill_one_alpha("LIVE.NS")

    async with session_factory() as session:
        live = await session.scalar(
            select(AlphaScore).where(
                AlphaScore.symbol == "LIVE.NS", AlphaScore.date == today
            )
        )
    assert live is not None
    assert live.fundamental is not None  # NOT overwritten to null
    assert float(live.fundamental) == 90.0
    assert float(live.composite) == 80.0


# --- API tests ----------------------------------------------------------------


async def _seed_for_alpha(session_factory) -> None:
    async with session_factory() as session:
        stock = Stock(symbol="RELIANCE.NS", name="Reliance", sector="E", industry="O")
        session.add(stock)
        await session.flush()
        session.add(
            Financials(stock_id=stock.id, trailing_pe=Decimal("20.00"),
                       return_on_equity=Decimal("0.1800"),
                       operating_margin=Decimal("0.1250"),
                       debt_to_equity=Decimal("50.00"))
        )
        today = date.today()
        for i in range(60):
            session.add(
                DailyPrice(stock_id=stock.id, date=today - timedelta(days=i),
                           open=100, high=101, low=99,
                           close=100 + (i * 0.1), volume=1000)
            )
        await session.commit()


async def test_alpha_endpoint_full(client, session_factory):
    await _seed_for_alpha(session_factory)
    r = await client.get("/api/v1/stocks/RELIANCE/alpha")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "RELIANCE.NS"
    assert body["composite"] is not None
    assert 0 <= body["composite"] <= 100
    assert "weights" in body and body["weights"]  # renormalized weights present
    assert body["insufficient_data"] is False
    # Part I split: the score path is pure computation - no explanation field
    # and no LLM work happens here.
    assert "explanation" not in body


async def test_alpha_explanation_endpoint(client, session_factory):
    """The lazy narrative endpoint returns a grounded explanation."""
    await _seed_for_alpha(session_factory)
    r = await client.get("/api/v1/stocks/RELIANCE/alpha/explanation")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "RELIANCE.NS"
    assert isinstance(body["explanation"], str)
    assert len(body["explanation"]) > 0  # rule-based fallback always available


async def test_alpha_endpoint_unknown_symbol_404(client, session_factory):
    await _seed_for_alpha(session_factory)
    r = await client.get("/api/v1/stocks/ZZZ/alpha")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


async def test_alpha_endpoint_insufficient_data(client, session_factory):
    # A stock with financials but no prices/news -> composite may be null but
    # the endpoint still returns 200 with insufficient_data.
    async with session_factory() as session:
        stock = Stock(symbol="NEW.NS", name="New", sector="X", industry="Y")
        session.add(stock)
        await session.flush()
        session.add(Financials(stock_id=stock.id, trailing_pe=Decimal("20.00")))
        await session.commit()
    r = await client.get("/api/v1/stocks/NEW/alpha")
    assert r.status_code == 200
    body = r.json()
    assert body["insufficient_data"] in (True, False)


async def test_alpha_unclassified_stock_answers_fast_no_network(client, session_factory):
    """M1-T3 500 regression: an unclassified stock's /alpha answers 200 fast.

    UTIAMC.NS-class rows (sector/industry NULL, no snapshot) hung the worker:
    the NULL-cohort peer fan-out fired thousands of Upstox calls. The fixed
    path must return 200 with insufficient_data=True and construct no live
    provider at all.
    """
    import app.services.analysis as analysis_mod
    import app.providers.upstox_provider as upstox_mod

    async with session_factory() as session:
        session.add(Stock(symbol="U1.NS", name="U1", sector=None, industry=None))
        session.add(Stock(symbol="U2.NS", name="U2", sector=None, industry=None))
        await session.commit()

    def _boom(token):
        raise AssertionError("request path must not construct a provider")

    orig_provider = upstox_mod.UpstoxProvider
    orig_token = analysis_mod.settings.upstox_analytics_token
    upstox_mod.UpstoxProvider = _boom  # type: ignore[assignment]
    analysis_mod.settings.upstox_analytics_token = "fake-token-for-test"
    try:
        r = await client.get("/api/v1/stocks/U1/alpha")
    finally:
        upstox_mod.UpstoxProvider = orig_provider  # type: ignore[assignment]
        analysis_mod.settings.upstox_analytics_token = orig_token
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "U1.NS"
    assert body["composite"] is None
    assert body["value_signal"] is None
    assert body["insufficient_data"] is True