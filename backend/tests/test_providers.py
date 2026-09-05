# Provider tests â€” no real network. Uses a fake MarketDataProvider to verify
# the interface contract, OHLCV mapping, and per-symbol error isolation (D19).

from datetime import date

import pytest

from app.providers.base import (
    Fundamentals,
    MarketDataProvider,
    OHLCV,
    StockProfile,
)
from app.providers.yfinance_provider import MarketDataError, YFinanceProvider


class FakeProvider(MarketDataProvider):
    """Deterministic provider: returns fixed OHLCV, raises for a set symbol."""

    def __init__(self, fail_symbol: str | None = None):
        self.fail_symbol = fail_symbol

    async def get_price_history(self, symbol: str, period: str) -> list[OHLCV]:
        if symbol == self.fail_symbol:
            raise MarketDataError(f"simulated failure for {symbol}")
        return [
            OHLCV(date=date(2026, 8, 18), open=1.0, high=2.0, low=0.5, close=1.5, volume=100)
        ]

    async def get_stock_profile(self, symbol: str) -> StockProfile:
        return StockProfile(symbol=symbol, name="Test", sector="X", industry="Y")

    async def get_fundamentals(self, symbol: str) -> Fundamentals:
        if symbol == self.fail_symbol:
            raise MarketDataError(f"simulated failure for {symbol}")
        return Fundamentals(
            symbol=symbol,
            market_cap=1_000_000.0,
            trailing_pe=20.0,
            return_on_equity=0.15,
            debt_to_equity=50.0,
        )


async def test_ohlcv_mapping_from_fake_provider():
    provider = FakeProvider()
    bars = await provider.get_price_history("TEST.NS", "1d")
    assert len(bars) == 1
    assert bars[0].close == 1.5
    assert bars[0].date == date(2026, 8, 18)


async def test_market_data_error_raised_on_failure():
    provider = FakeProvider(fail_symbol="BAD.NS")
    with pytest.raises(MarketDataError):
        await provider.get_price_history("BAD.NS", "1d")


async def test_yfinance_provider_is_interface_compliant():
    # Just verify the class satisfies the ABC (import + instantiate is enough).
    p = YFinanceProvider()
    assert isinstance(p, MarketDataProvider)


async def test_ingest_universe_isolates_failures(session_factory, monkeypatch):
    """One failing symbol must not abort the whole run (D19)."""
    import app.jobs as jobs_module

    from app.jobs import ingest_universe
    from app.models import Stock, Universe, stock_universe

    # Seed one stock + a nifty50 universe + the link, via the test factory.
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

    # Point jobs.py at the TEST DB (its default SessionLocal is the prod engine).
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    # Fake provider that fails for RELIANCE.NS (the only symbol in the universe).
    provider = FakeProvider(fail_symbol="RELIANCE.NS")

    result = await ingest_universe(provider, batch_size=10)
    assert result["errors"] == 1
    assert result["bars"] == 0
