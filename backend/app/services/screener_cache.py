# Screener snapshot cache (work list item 14).
#
# GET /screener used to analyse every stock in the ranked universe on EVERY
# request: one stock lookup plus analyze_stock (financials, peers, peer
# financials) per symbol, about 4,000 database round trips from Render's
# free instance to Neon for each page load and each sort click.
#
# The inputs only change when an ingestion/ranking job writes, so the full
# analysed table is built once and reused. The router still filters, sorts and
# pages it per request, exactly as before; analyze_stock is unchanged, so the
# results are identical.
#
# Freshness: the snapshot is rebuilt when
#   - the newest finished job_runs row changes (a nightly, rank or manual
#     pass completed: the data may have changed), or
#   - it is older than SNAPSHOT_MAX_AGE_SECONDS (safety net).
# The freshness check is one tiny query on job_runs (a few hundred rows).
#
# Scope: in-process memory, like the rate limiter. Render runs one process;
# a restart simply rebuilds on the first request.

import asyncio
import time
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobRun, Stock
from app.repositories.stocks import active_universe_filter
from app.services import analysis

SNAPSHOT_MAX_AGE_SECONDS = 3600


@dataclass(frozen=True)
class ScreenRow:
    symbol: str
    name: str
    sector: str | None
    industry: str | None
    profitability: int | None
    solvency: int | None
    valuation_status: str | None
    margin_pct: float | None


@dataclass
class _Snapshot:
    stamp: object
    built_at: float
    rows: list[ScreenRow]


_snapshot: _Snapshot | None = None
_lock: asyncio.Lock | None = None


def reset_cache() -> None:
    """Test hook: forget the snapshot (and the lock, which is loop-bound)."""
    global _snapshot, _lock
    _snapshot = None
    _lock = None


async def _data_stamp(session: AsyncSession) -> object:
    """Changes whenever any job finishes (the only writer of screener inputs)."""
    return await session.scalar(select(func.max(JobRun.finished_at)))


def _is_fresh(snap: _Snapshot | None, stamp: object) -> bool:
    return (
        snap is not None
        and snap.stamp == stamp
        and time.monotonic() - snap.built_at < SNAPSHOT_MAX_AGE_SECONDS
    )


async def _build(session: AsyncSession) -> list[ScreenRow]:
    """Analyse every equity in the active universe (the old per-request loop)."""
    stmt = select(Stock).where(Stock.is_etf.is_(False))
    stmt = active_universe_filter(stmt).order_by(Stock.symbol)
    stocks = (await session.execute(stmt)).scalars().all()
    rows: list[ScreenRow] = []
    for stock in stocks:
        a = await analysis.analyze_stock(session, stock)
        rows.append(
            ScreenRow(
                symbol=a.symbol,
                name=a.name,
                sector=a.sector,
                industry=a.industry,
                profitability=a.profitability,
                solvency=a.solvency,
                valuation_status=a.valuation_status,
                margin_pct=a.margin_pct,
            )
        )
    return rows


async def get_rows(session: AsyncSession) -> list[ScreenRow]:
    """The analysed universe, rebuilt only when the data may have changed.

    Concurrent first requests share one build (the lock), instead of each
    running the full analysis.
    """
    global _snapshot, _lock
    stamp = await _data_stamp(session)
    if _is_fresh(_snapshot, stamp):
        return _snapshot.rows  # type: ignore[union-attr]
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        if _is_fresh(_snapshot, stamp):  # built while we waited
            return _snapshot.rows  # type: ignore[union-attr]
        rows = await _build(session)
        _snapshot = _Snapshot(stamp=stamp, built_at=time.monotonic(), rows=rows)
        return rows
