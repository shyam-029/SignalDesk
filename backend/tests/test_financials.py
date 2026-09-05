# Tests for the financials sub-phase: model, provider mapping, ingestion.
#
# No network: uses FakeProvider from test_providers (mocked provider). All DB
# writes go to signaldesk_test via session_factory / monkeypatched SessionLocal.

from decimal import Decimal

import pytest
from sqlalchemy import select

import app.jobs as jobs_module
from app.jobs import ingest_financials
from app.models import Financials, Stock, Universe, stock_universe
from app.providers.base import Fundamentals
from app.providers.yfinance_provider import MarketDataError, YFinanceProvider
from tests.test_providers import FakeProvider


async def seed_one_stock(session_factory) -> None:
    """Insert one stock + nifty50 universe + link in the test DB."""
    async with session_factory() as session:
        stock = Stock(symbol="RELIANCE.NS", name="Reliance", sector="Energy")
        session.add(stock)
        await session.flush()
        universe = Universe(name="nifty250")
        session.add(universe)
        await session.flush()
        await session.execute(
            stock_universe.insert().values(universe_id=universe.id, stock_id=stock.id)
        )
        await session.commit()


async def test_yfinance_provider_implements_get_fundamentals():
    """Interface compliance â€” YFinanceProvider must implement the new method."""
    p = YFinanceProvider()
    assert hasattr(p, "get_fundamentals")


async def test_fake_provider_fundamentals_values():
    """FakeProvider returns the Fundamentals fields the ingestion maps."""
    p = FakeProvider()
    f = await p.get_fundamentals("RELIANCE.NS")
    assert isinstance(f, Fundamentals)
    assert f.trailing_pe == 20.0
    assert f.return_on_equity == 0.15
    assert f.debt_to_equity == 50.0


async def test_ingest_financials_upserts_one_row(session_factory, monkeypatch):
    """A single ingestion writes exactly one financials row for the stock."""
    await seed_one_stock(session_factory)
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    result = await ingest_financials(FakeProvider(), batch_size=10)
    assert result["rows"] == 1
    assert result["errors"] == 0

    async with session_factory() as session:
        row = await session.scalar(select(Financials))
        assert row is not None
        assert row.trailing_pe == Decimal("20.00")
        assert row.return_on_equity == Decimal("0.1500")
        assert row.debt_to_equity == Decimal("50.00")


async def test_ingest_financials_idempotent(session_factory, monkeypatch):
    """Re-running keeps one row per stock (upsert, not duplicate)."""
    await seed_one_stock(session_factory)
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    await ingest_financials(FakeProvider(), batch_size=10)
    await ingest_financials(FakeProvider(), batch_size=10)

    async with session_factory() as session:
        rows = (await session.execute(select(Financials))).scalars().all()
        assert len(rows) == 1


async def test_ingest_financials_isolates_failures(session_factory, monkeypatch):
    """A failing symbol is logged/isolated; run continues (D19)."""
    await seed_one_stock(session_factory)
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    result = await ingest_financials(FakeProvider(fail_symbol="RELIANCE.NS"), batch_size=10)
    assert result["errors"] == 1
    assert result["rows"] == 0
