# Benchmark ingestion tests (M1-T6, Plan 13/14). Zero-network: a fake
# provider serves canned index bars; the DB is signaldesk_test via the
# monkeypatched SessionLocal (same pattern as test_jobs_status.py).
#
# Covered:
#   1. benchmark upsert writes one benchmarks row + bars per symbol
#   2. reruns are idempotent (UNIQUE(benchmark_id, date), no duplicates)
#   3. per-index failure isolation (D19)
#   4. top-1000 universe selection (benchmarks never enter the equity universe)
#   5. job pass recording via _record_pass
#   6. benchmark data does not interfere with equity ranking (no Stock rows)

from datetime import date

import pytest
from sqlalchemy import func, select

from app import jobs as jobs_module
from app.jobs import BENCHMARK_SYMBOLS, ingest_benchmarks
from app.models import Benchmark, BenchmarkPrice, Stock, Universe, stock_universe
from app.providers.base import MarketDataError, MarketDataProvider, OHLCV


class FakeIndexProvider(MarketDataProvider):
    """Deterministic index provider: canned bars; explodes for one symbol."""

    name = "fake-index"

    def __init__(self, fail_symbol: str | None = None):
        self.fail_symbol = fail_symbol

    async def get_price_history(self, symbol: str, period: str):
        if symbol == self.fail_symbol:
            raise MarketDataError(f"simulated benchmark failure for {symbol}")
        return [
            OHLCV(date=date(2026, 9, 4), open=100, high=101, low=99,
                  close=100.5, volume=1000, source="fake-index"),
            OHLCV(date=date(2026, 9, 5), open=100.5, high=102, low=100,
                  close=101.5, volume=1200, source="fake-index"),
        ]

    async def get_stock_profile(self, symbol: str):
        from app.providers.base import StockProfile
        return StockProfile(symbol=symbol, name=symbol, sector=None, industry=None)

    async def get_fundamentals(self, symbol: str):
        from app.providers.base import Fundamentals
        return Fundamentals(symbol=symbol)


async def _benchmark_counts(session_factory):
    async with session_factory() as session:
        n_bench = await session.scalar(select(func.count(Benchmark.id)))
        n_bars = await session.scalar(select(func.count(BenchmarkPrice.id)))
        n_stocks = await session.scalar(select(func.count(Stock.id)))
        return n_bench, n_bars, n_stocks


async def test_ingest_benchmarks_writes_rows(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    result = await ingest_benchmarks(
        FakeIndexProvider(), symbols=("^NSEI", "^NSEBANK"), batch_size=10
    )
    assert result == {"fetched": 2, "bars": 4, "errors": 0}
    n_bench, n_bars, n_stocks = await _benchmark_counts(session_factory)
    assert n_bench == 2
    assert n_bars == 4
    assert n_stocks == 0  # benchmarks never enter the equity catalog


async def test_ingest_benchmarks_idempotent_rerun(session_factory, monkeypatch):
    """Reruns upsert the same bars: no duplicate benchmark_prices rows."""
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    provider = FakeIndexProvider()
    first = await ingest_benchmarks(provider, symbols=("^NSEI",), batch_size=10)
    second = await ingest_benchmarks(provider, symbols=("^NSEI",), batch_size=10)
    assert first["bars"] == 2
    assert second["bars"] == 2  # offered again (overwrite), never duplicated
    assert second["errors"] == 0
    async with session_factory() as session:
        n_bars = await session.scalar(select(func.count(BenchmarkPrice.id)))
        assert n_bars == 2


async def test_ingest_benchmarks_isolates_failures(session_factory, monkeypatch):
    """One failing index never aborts the pass (D19)."""
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    result = await ingest_benchmarks(
        FakeIndexProvider(fail_symbol="^NSEI"),
        symbols=("^NSEI", "^NSEBANK"),
        batch_size=10,
    )
    assert result["errors"] == 1
    assert result["fetched"] == 1
    assert result["bars"] == 2  # the healthy index still ingested


async def test_benchmarks_never_enter_equity_universe(session_factory, monkeypatch):
    """Top-1000 universe selection: benchmark symbols are not universe members.

    The nightly equity passes read stock_universe membership; benchmark rows
    live in benchmarks/benchmark_prices, so even a "^NSEI"-named equity row
    could never be selected — and none exists.
    """
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    await ingest_benchmarks(FakeIndexProvider(), symbols=("^NSEI",), batch_size=10)

    async with session_factory() as session:
        session.add(Universe(name=jobs_module.UNIVERSE_NAME))
        session.add(Stock(symbol="AAA.NS", name="AAA", sector="IT"))
        await session.flush()
        uni = await session.scalar(
            select(Universe).where(Universe.name == jobs_module.UNIVERSE_NAME)
        )
        stock = await session.scalar(select(Stock).where(Stock.symbol == "AAA.NS"))
        await session.execute(
            stock_universe.insert().values(universe_id=uni.id, stock_id=stock.id)
        )
        await session.commit()

    async with session_factory() as session:
        symbols = await jobs_module._get_universe_symbols(session)
    assert symbols == ["AAA.NS"]
    assert "^NSEI" not in symbols


async def test_benchmark_pass_records_job_run(session_factory, monkeypatch):
    """The benchmark pass records a job_runs row like every other pass."""
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    status = await jobs_module._record_pass(
        "ingest_benchmarks", ingest_benchmarks, FakeIndexProvider(),
        ("^NSEI",),
    )
    assert status == "success"
    async with session_factory() as session:
        from app.models import JobRun

        row = await session.scalar(
            select(JobRun)
            .where(JobRun.job_name == "ingest_benchmarks")
            .order_by(JobRun.id.desc())
        )
    assert row is not None
    assert row.status == "success"
    assert row.items_processed == 1


def test_benchmark_symbol_list_matches_plan():
    """The required Plan 13 symbols are exactly the ingested set."""
    assert set(BENCHMARK_SYMBOLS) == {"^NSEI", "^NSEBANK", "^CNXIT", "^CRSLDX"}
