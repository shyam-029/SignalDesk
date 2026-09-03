# Phase 6 tests — stock detail + technicals endpoints + CORS. Zero-network:
# prices/financials are seeded directly into signaldesk_test; expected indicator
# values are computed with the SAME pure functions the endpoint uses.

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.main import app
from app.models import DailyPrice, Financials, Stock
from app.services import indicators


async def _make_stock(session_factory, symbol: str, n_bars: int, industry: str = "Oil"):
    """Insert a stock with n deterministic daily bars; return (id, closes)."""
    async with session_factory() as session:
        stock = Stock(symbol=symbol, name=symbol, sector="Energy", industry=industry)
        session.add(stock)
        await session.flush()

        today = date.today()
        closes = []
        rows = []
        for i in range(n_bars):
            close = 100.0 + (i % 7) * 1.5
            closes.append(close)
            rows.append(
                DailyPrice(
                    stock_id=stock.id,
                    date=today - timedelta(days=n_bars - 1 - i),
                    open=close - 0.5,
                    high=close + 1.0,
                    low=close - 1.0,
                    close=close,
                    volume=1000 + i,
                )
            )
        session.add_all(rows)
        await session.commit()
        return stock.id, closes


# --- CORS ----------------------------------------------------------------------


async def test_cors_preflight_from_allowed_origin(client):
    r = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


async def test_cors_preflight_allows_configured_methods(client):
    r = await client.options(
        "/api/v1/stocks/RELIANCE/explain",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


async def test_cors_disallowed_origin_gets_no_allow_header(client):
    r = await client.get("/health", headers={"Origin": "http://evil.example"})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers


# --- GET /stocks/{symbol} --------------------------------------------------------


async def test_stock_detail_returns_profile_and_quote(client, session_factory):
    await _make_stock(session_factory, "RELIANCE.NS", 3)

    r = await client.get("/api/v1/stocks/RELIANCE")
    assert r.status_code == 200
    body = r.json()

    assert body["symbol"] == "RELIANCE.NS"
    assert body["name"] == "RELIANCE.NS"
    assert body["sector"] == "Energy"
    assert body["industry"] == "Oil"
    assert body["market_cap"] is None  # no financial snapshot → honest null

    q = body["quote"]
    assert q["last_price"] == pytest.approx(103.0)   # closes: 100, 101.5, 103
    assert q["prev_close"] == pytest.approx(101.5)
    assert q["change_abs"] == pytest.approx(1.5)
    assert q["change_pct"] == pytest.approx(1.48)    # 1.5/101.5*100 → 1.48
    assert q["open"] == pytest.approx(102.5)
    assert q["high"] == pytest.approx(104.0)
    assert q["low"] == pytest.approx(102.0)
    assert q["volume"] == 1002
    assert q["date"] is not None


async def test_stock_detail_includes_market_cap_when_present(client, session_factory):
    stock_id, _ = await _make_stock(session_factory, "TCS.NS", 2)
    async with session_factory() as session:
        session.add(Financials(stock_id=stock_id, market_cap=1500000000000))
        await session.commit()

    r = await client.get("/api/v1/stocks/TCS.NS")
    assert r.status_code == 200
    body = r.json()
    assert body["market_cap"] == 1500000000000.0


async def test_stock_detail_without_prices_returns_null_quote(client, session_factory):
    async with session_factory() as session:
        session.add(Stock(symbol="EMPTY.NS", name="Empty", sector="IT"))
        await session.commit()

    r = await client.get("/api/v1/stocks/EMPTY.NS")
    assert r.status_code == 200
    body = r.json()
    assert body["quote"]["last_price"] is None
    assert body["quote"]["change_pct"] is None
    assert body["quote"]["date"] is None


async def test_stock_detail_unknown_symbol_404_envelope(client):
    r = await client.get("/api/v1/stocks/NOPE")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert "NOPE.NS" in body["error"]["message"]
    assert "request_id" in body["error"]


# --- GET /stocks/{symbol}/technicals ------------------------------------------------


async def test_technicals_matches_pure_indicator_functions(client, session_factory):
    _, closes = await _make_stock(session_factory, "INFO.NS", 40)

    r = await client.get("/api/v1/stocks/INFO/technicals")
    assert r.status_code == 200
    body = r.json()

    assert body["symbol"] == "INFO.NS"
    assert body["insufficient_data"] is False
    assert body["closes_used"] == 40

    # Values must be exactly what the shared pure functions produce.
    assert body["sma20"] == pytest.approx(indicators.sma(closes, 20))
    assert body["ema12"] == pytest.approx(indicators.ema(closes, 12))
    assert body["rsi14"] == pytest.approx(indicators.rsi(closes, 14))
    macd_expected = indicators.macd(closes)
    assert body["macd"]["macd"] == pytest.approx(macd_expected["macd"])
    assert body["macd"]["signal"] == pytest.approx(macd_expected["signal"])
    assert body["macd"]["histogram"] == pytest.approx(macd_expected["histogram"])

    scored = indicators.score_technicals(closes)
    assert body["score"] == scored["score"]
    assert body["components"]["trend"] == scored["components"]["trend"]
    assert body["components"]["momentum"] == scored["components"]["momentum"]
    assert body["components"]["reversion"] == scored["components"]["reversion"]
    assert body["last_close"] == pytest.approx(closes[-1])


async def test_technicals_insufficient_history_flags_data_state(client, session_factory):
    await _make_stock(session_factory, "THIN.NS", 5)

    r = await client.get("/api/v1/stocks/THIN/technicals")
    assert r.status_code == 200
    body = r.json()
    assert body["insufficient_data"] is True
    assert body["score"] is None
    assert body["sma20"] is None
    assert body["macd"]["histogram"] is None
    assert body["closes_used"] == 5


async def test_technicals_unknown_symbol_404_envelope(client):
    r = await client.get("/api/v1/stocks/GHOST/technicals")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
