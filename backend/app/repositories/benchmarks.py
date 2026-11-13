# Benchmark repository — index catalog + OHLCV bars (M1-T6, Plan 14).
#
# Benchmarks live OUTSIDE the equity catalog: no Stock rows, no universe
# membership, no peer-set participation. Two helpers mirror the existing
# equity patterns: get-or-create for the index row, bulk upsert for bars
# (UNIQUE(benchmark_id, date) keeps reruns idempotent).

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Benchmark, BenchmarkPrice
from app.providers.base import OHLCV
from app.repositories.upsert_guard import any_distinct


async def get_or_create_benchmark(
    session: AsyncSession,
    symbol: str,
    name: str | None,
    source: str | None = None,
    kind: str = "index",
) -> Benchmark:
    """Get-or-create the benchmarks row for an index symbol (seed.py pattern)."""
    row = await session.scalar(select(Benchmark).where(Benchmark.symbol == symbol))
    if row is None:
        row = Benchmark(symbol=symbol, name=name, kind=kind, source=source)
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

    On conflict with (benchmark_id, date) the stored bar is overwritten with
    field-level COALESCE — same defensive shape as the equity price upsert in
    jobs._fetch_one_symbol (incident 2026-09-09): a column the provider did
    not supply must never blank a previously-good stored value.
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
    new_values = {
        col: func.coalesce(getattr(stmt.excluded, col), getattr(BenchmarkPrice, col))
        for col in ("open", "high", "low", "close", "volume")
    }
    stmt = stmt.on_conflict_do_update(
        constraint="uq_benchmark_prices_benchmark_date",
        set_=new_values,
        # No-op guard: unchanged re-offered bars write nothing (upsert_guard).
        where=any_distinct(BenchmarkPrice, new_values),
    )
    await session.execute(stmt)
    await session.commit()
    return len(bars)


async def list_benchmarks(session: AsyncSession) -> list[Benchmark]:
    """Every stored benchmark index, ordered by symbol."""
    rows = await session.execute(select(Benchmark).order_by(Benchmark.symbol))
    return list(rows.scalars())


# Cache for get_closes_cached: symbol -> (fingerprint, closes).
_closes_cache: dict[str, tuple[tuple, list[tuple]]] = {}


def reset_cache() -> None:
    """Test hook: forget cached benchmark closes."""
    _closes_cache.clear()


async def _closes_fingerprint(session: AsyncSession, symbol: str) -> tuple:
    """(row count, latest date, sum of closes) of one index's stored bars.

    Computed by the database and returned as one row, so checking it costs
    almost nothing. Any added, removed or revised close changes it.
    """
    row = (
        await session.execute(
            select(
                func.count(BenchmarkPrice.date),
                func.max(BenchmarkPrice.date),
                func.sum(BenchmarkPrice.close),
            )
            .join(Benchmark, Benchmark.id == BenchmarkPrice.benchmark_id)
            .where(Benchmark.symbol == symbol)
        )
    ).one()
    return tuple(row)


async def get_closes_cached(session: AsyncSession, symbol: str) -> list[tuple]:
    """get_closes(), re-read only when the index's stored bars changed.

    The risk endpoint needs the NIFTY 50 series for every stock; without
    this, building 1,000 stock snapshots read the same ~500 rows 1,000
    times (2026-11-13). Returns exactly what get_closes() would.
    """
    fp = await _closes_fingerprint(session, symbol)
    hit = _closes_cache.get(symbol)
    if hit is not None and hit[0] == fp:
        return hit[1]
    closes = await get_closes(session, symbol)
    _closes_cache[symbol] = (fp, closes)
    return closes


async def get_closes(session: AsyncSession, symbol: str) -> list[tuple]:
    """One index's stored (date, close) pairs, oldest first; [] when absent."""
    rows = await session.execute(
        select(BenchmarkPrice.date, BenchmarkPrice.close)
        .join(Benchmark, Benchmark.id == BenchmarkPrice.benchmark_id)
        .where(Benchmark.symbol == symbol)
        .order_by(BenchmarkPrice.date.asc())
    )
    return [(day, float(close)) for day, close in rows.all()]
