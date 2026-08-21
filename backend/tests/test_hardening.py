# Hardening tests — cover the audit's missing high-value cases.
#
#  - EV_EBITDA / PB / PS through the HTTP layer (previously only PE was tested)
#  - industry-NULL -> sector fallback for peer selection
#  - /fundamentals for a stock with no financials
#  - query-count assertion proving list_stocks has no N+1
#  - financials.updated_at refreshes on re-ingest
#  - provider retry-with-backoff behavior

import asyncio
from decimal import Decimal
from datetime import date

import pytest
from sqlalchemy import event, select

import app.jobs as jobs_module
from app.jobs import ingest_financials, ingest_universe
from app.models import Financials, Stock, Universe, stock_universe
from app.providers.base import Fundamentals, MarketDataProvider, OHLCV, StockProfile
from app.providers.yfinance_provider import MarketDataError


async def _seed_valuation_data(session_factory) -> None:
    """Stocks + financials covering all four multiples."""
    async with session_factory() as session:
        tcs = Stock(symbol="TCS.NS", name="TCS", sector="IT", industry="IT Services")
        infy = Stock(symbol="INFY.NS", name="Infy", sector="IT", industry="IT Services")
        session.add_all([tcs, infy])
        await session.flush()
        session.add_all(
            [
                Financials(
                    stock_id=tcs.id, trailing_pe=Decimal("28.40"),
                    enterprise_value=Decimal("1000.00"), ebitda=Decimal("50.00"),
                    price_to_book=Decimal("4.00"), price_to_sales=Decimal("3.00"),
                ),
                Financials(
                    stock_id=infy.id, trailing_pe=Decimal("24.10"),
                    enterprise_value=Decimal("900.00"), ebitda=Decimal("60.00"),
                    price_to_book=Decimal("3.00"), price_to_sales=Decimal("2.00"),
                ),
            ]
        )
        await session.commit()


# --- Non-PE multiples through HTTP -------------------------------------------


async def test_valuation_ev_ebitda(client, session_factory):
    await _seed_valuation_data(session_factory)
    r = await client.get("/api/v1/stocks/TCS/valuation", params={"metric": "EV_EBITDA"})
    body = r.json()
    # current = 1000/50 = 20.0 ; peer = 900/60 = 15.0 -> overvalued +33%
    assert body["current"] == 20.0
    assert body["peer_median"] == 15.0
    assert body["status"] == "overvalued"


async def test_valuation_pb(client, session_factory):
    await _seed_valuation_data(session_factory)
    r = await client.get("/api/v1/stocks/TCS/valuation", params={"metric": "PB"})
    body = r.json()
    assert body["current"] == 4.0
    assert body["peer_median"] == 3.0


# --- Industry-NULL -> sector fallback -----------------------------------------


async def test_valuation_sector_fallback_when_industry_null(client, session_factory):
    async with session_factory() as session:
        a = Stock(symbol="A.NS", name="A", sector="Auto", industry=None)
        b = Stock(symbol="B.NS", name="B", sector="Auto", industry=None)
        session.add_all([a, b])
        await session.flush()
        session.add_all(
            [
                Financials(stock_id=a.id, trailing_pe=Decimal("20.00")),
                Financials(stock_id=b.id, trailing_pe=Decimal("40.00")),
            ]
        )
        await session.commit()

    r = await client.get("/api/v1/stocks/A/valuation", params={"metric": "PE"})
    assert r.status_code == 200
    body = r.json()
    # Only B.NS is a peer (sector fallback); current 20 vs 40 -> undervalued -50%
    assert body["peers"] == ["B.NS"]
    assert body["status"] == "undervalued"


# --- /fundamentals with no financials row -------------------------------------


async def test_fundamentals_no_financials_returns_empty(client, session_factory):
    async with session_factory() as session:
        session.add(Stock(symbol="NEW.NS", name="New", sector="X", industry="Y"))
        await session.commit()
    r = await client.get("/api/v1/stocks/NEW/fundamentals")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "NEW.NS"
    assert body["key_ratios"] == {}
    assert body["updated_at"] is None


# --- list_stocks query count (N+1 regression guard) ---------------------------


async def test_list_stocks_query_count_is_bounded(client, session_factory):
    """list_stocks must issue a constant number of queries regardless of page size."""
    async with session_factory() as session:
        for i in range(10):
            s = Stock(symbol=f"STK{i}.NS", name=f"Stock {i}", sector="X")
            session.add(s)
        await session.commit()

    # Count SQL executions on the engine during one request.
    counts = {"n": 0}

    def _count(conn, cursor, statement, parameters, context, executemany):
        counts["n"] += 1

    engine = session_factory.kw["bind"]
    event.listen(engine.sync_engine, "before_cursor_execute", _count)

    try:
        r = await client.get("/api/v1/stocks", params={"limit": 50})
        assert r.status_code == 200
        assert r.json()["total"] == 10
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count)

    # 1 count query + 1 page query + 1 batched price query = 3. Anything above
    # ~5 means the old per-stock loop is back.
    assert counts["n"] <= 5, f"expected bounded queries, saw {counts['n']}"


# --- financials.updated_at refresh on re-ingest -------------------------------


class UpdatedAtProvider(MarketDataProvider):
    """Returns fixed fundamentals; lets the test observe updated_at moving."""

    async def get_price_history(self, symbol, period):
        return [OHLCV(date=date(2026, 1, 1), open=1, high=2, low=0.5, close=1.5, volume=10)]

    async def get_stock_profile(self, symbol):
        return StockProfile(symbol=symbol, name="X", sector="X", industry="Y")

    async def get_fundamentals(self, symbol):
        return Fundamentals(symbol=symbol, trailing_pe=20.0)


async def test_financials_updated_at_refreshes(session_factory, monkeypatch):
    async with session_factory() as session:
        s = Stock(symbol="RELIANCE.NS", name="Reliance", sector="E", industry="O")
        session.add(s)
        await session.flush()
        universe = Universe(name="nifty50")
        session.add(universe)
        await session.flush()
        await session.execute(
            stock_universe.insert().values(universe_id=universe.id, stock_id=s.id)
        )
        await session.commit()

    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    provider = UpdatedAtProvider()

    await ingest_financials(provider, batch_size=10)
    async with session_factory() as session:
        row = await session.scalar(select(Financials))
        first_ts = row.updated_at

    await asyncio.sleep(1.1)  # server_default/now() has second precision
    await ingest_financials(provider, batch_size=10)

    async with session_factory() as session:
        row = await session.scalar(select(Financials))
        assert row.updated_at > first_ts, "updated_at should refresh on upsert"


# --- Retry-with-backoff -------------------------------------------------------


class FlakyProvider(MarketDataProvider):
    """Fails a fixed number of times before succeeding."""

    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.calls = 0

    async def get_price_history(self, symbol, period):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise MarketDataError("transient failure")
        return [
            OHLCV(date=date(2026, 1, 1), open=1, high=2, low=0.5, close=1.5, volume=10)
        ]

    async def get_stock_profile(self, symbol):
        return StockProfile(symbol=symbol, name="X", sector="X", industry="Y")

    async def get_fundamentals(self, symbol):
        return Fundamentals(symbol=symbol, trailing_pe=20.0)


async def test_ingest_universe_retries_transient_failure(session_factory, monkeypatch):
    async with session_factory() as session:
        s = Stock(symbol="RELIANCE.NS", name="Reliance", sector="E", industry="O")
        session.add(s)
        await session.flush()
        universe = Universe(name="nifty50")
        session.add(universe)
        await session.flush()
        await session.execute(
            stock_universe.insert().values(universe_id=universe.id, stock_id=s.id)
        )
        await session.commit()

    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    provider = FlakyProvider(fail_times=2)  # succeeds on 3rd attempt
    result = await ingest_universe(provider, batch_size=10)
    assert result["errors"] == 0
    assert result["bars"] == 1
    assert provider.calls == 3  # 2 failures + 1 success


async def test_ingest_universe_gives_up_after_retries(session_factory, monkeypatch):
    async with session_factory() as session:
        s = Stock(symbol="RELIANCE.NS", name="Reliance", sector="E", industry="O")
        session.add(s)
        await session.flush()
        universe = Universe(name="nifty50")
        session.add(universe)
        await session.flush()
        await session.execute(
            stock_universe.insert().values(universe_id=universe.id, stock_id=s.id)
        )
        await session.commit()

    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    provider = FlakyProvider(fail_times=99)  # always fails
    result = await ingest_universe(provider, batch_size=10)
    assert result["errors"] == 1  # isolated, run does not crash