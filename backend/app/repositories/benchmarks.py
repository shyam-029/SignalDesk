# Benchmark repository — index catalog + OHLCV bars (M1-T6, Plan 14).
#
# Benchmarks live OUTSIDE the equity catalog: no Stock rows, no universe
# membership, no peer-set participation. Two helpers mirror the existing
# equity patterns: get-or-create for the index row, bulk upsert for bars
# (UNIQUE(benchmark_id, date) keeps reruns idempotent).

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Benchmark, BenchmarkPrice
from app.providers.base import OHLCV


async def get_or_create_benchmark(
    session: AsyncSession, symbol: str, name: str | None, source: str | None = None
) -> Benchmark:
    """Get-or-create the benchmarks row for an index symbol (seed.py pattern)."""
    row = await session.scalar(select(Benchmark).where(Benchmark.symbol == symbol))
    if row is None:
        row = Benchmark(symbol=symbol, name=name, kind="index", source=source)
        session.add(row)
        await session.flush()
        return row
    # Refresh the display name when the provider supplies a better one; never
    # blank a stored name with a missing one.
    if name and row.name != name:
        row.name = name
    if source:
        row.source = source
    return row


async def upsert_bars(
    session: AsyncSession, benchmark_id: int, bars: list[OHLCV]
) -> int:
    """Bulk-upsert one index's bars; returns the number of bars offered.

    On conflict with (benchmark_id, date) the stored bar is overwritten —
    same idempotent shape as the equity price upsert in jobs._fetch_one_symbol.
    """
    if not bars:
        return 0
    stmt = pg_insert(BenchmarkPrice).values(
        [
            {
                "benchmark_id": benchmark_id,
                "date": b.date,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ]
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_benchmark_prices_benchmark_date",
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
        },
    )
    await session.execute(stmt)
    await session.commit()
    return len(bars)


async def list_benchmarks(session: AsyncSession) -> list[Benchmark]:
    """Every stored benchmark index, ordered by symbol."""
    rows = await session.execute(select(Benchmark).order_by(Benchmark.symbol))
    return list(rows.scalars())
