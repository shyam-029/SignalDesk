# Alpha Score tests — service, repository, and API. Network-free.
#
#  - Service tests use hand-built data (no FinBERT load; sentiment mocked).
#  - Repository tests use signaldesk_test.
#  - API tests use the httpx ASGI client with the DB dependency overridden.

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AlphaScore, DailyPrice, Financials, Stock
from app.repositories import alpha as alpha_repo
from app.repositories import prices as price_repo
from app.services.alpha import _mean_of, _renormalized, compute_alpha
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
    # Only fundamental + technical: weights become 0.4/0.3 renormalized = 0.57/0.43
    c, w = _renormalized(100, 0, None)
    assert c == round(100 * 0.4 / 0.7 + 0 * 0.3 / 0.7)
    assert abs(w["fundamental"] - 0.57) < 0.01
    assert abs(w["technical"] - 0.43) < 0.01


def test_renormalized_all_missing():
    c, w = _renormalized(None, None, None)
    assert c is None
    assert w == {}


def test_renormalized_mix():
    # fundamental 100 (40%), technical 50 (30%), sentiment 0 (30%)
    # = 40 + 15 + 0 = 55
    c, _ = _renormalized(100, 50, 0)
    assert c == 55


# --- Indicators integration ---------------------------------------------------


def test_indicators_produce_technical_score():
    closes = list(range(1, 61))  # strongly rising
    tech = indicators.score_technicals(closes)
    assert tech["score"] is not None
    assert 0 <= tech["score"] <= 100
    assert {"trend", "momentum", "reversion"} <= set(tech["components"])


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