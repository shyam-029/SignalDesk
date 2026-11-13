# Price repository — batched lookups to avoid N+1 queries.
#
# list_stocks previously ran 2 queries per stock. get_two_latest runs ONE query
# with a window function (ROW_NUMBER partitioned by stock) to fetch the latest
# two price rows for many stocks at once.

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.models import DailyPrice
from app.repositories.batch_memo import memo_for


async def get_two_latest(
    session: AsyncSession, stock_ids: list[int]
) -> dict[int, list[DailyPrice]]:
    """Return {stock_id: [latest, second_latest]} for the given stocks.

    Uses a window function to number rows newest-first within each stock, then
    keeps rank <= 2. Rows within a group are returned newest-first.
    """
    if not stock_ids:
        return {}

    window = (
        select(
            DailyPrice,
            func.row_number()
            .over(partition_by=DailyPrice.stock_id, order_by=DailyPrice.date.desc())
            .label("rn"),
        )
        .where(DailyPrice.stock_id.in_(stock_ids))
        .subquery()
    )

    # Reference the subquery's columns explicitly to avoid ORM ambiguity.
    from sqlalchemy.orm import aliased

    ranked = aliased(DailyPrice, window)
    result = await session.execute(
        select(ranked).where(window.c.rn <= 2)
    )
    rows = result.scalars().all()

    out: dict[int, list[DailyPrice]] = {}
    for r in rows:
        out.setdefault(r.stock_id, []).append(r)
    return out


async def get_return_1y(
    session: AsyncSession, stock_ids: list[int], days: int = 366
) -> dict[int, tuple[float, float | None]]:
    """Return {stock_id: (latest_close, year_ago_close | None)}, batched.

    The anchor is each stock's OWN latest stored bar (the same as-of
    convention the performance endpoint uses); the year-ago close is the
    last close on or before (latest_date - days). A stock with no bars is
    absent from the mapping; a stock whose history is shorter than the
    window gets None — the caller reports the missing return honestly
    (never interpolated, never annualized from a partial window).

    Two batched queries (latest pick + year-ago pick) so N stocks cost O(1)
    queries, honoring the N+1 guard.
    """
    if not stock_ids:
        return {}

    # Latest close per stock: DISTINCT ON keeps the newest bar's close.
    latest_rows = await session.execute(
        select(DailyPrice.stock_id, DailyPrice.close)
        .where(DailyPrice.stock_id.in_(stock_ids))
        .distinct(DailyPrice.stock_id)
        .order_by(DailyPrice.stock_id, DailyPrice.date.desc())
    )
    out: dict[int, tuple[float, float | None]] = {
        stock_id: (float(close), None) for stock_id, close in latest_rows.all()
    }

    # Year-ago close per stock: anchor each stock on its own max(date) and
    # keep the single newest bar at or before that date minus `days`.
    anchors = (
        select(
            DailyPrice.stock_id.label("stock_id"),
            func.max(DailyPrice.date).label("max_date"),
        )
        .where(DailyPrice.stock_id.in_(stock_ids))
        .group_by(DailyPrice.stock_id)
        .subquery()
    )
    ago_rows = await session.execute(
        select(DailyPrice.stock_id, DailyPrice.close)
        .join(anchors, anchors.c.stock_id == DailyPrice.stock_id)
        .where(DailyPrice.date <= anchors.c.max_date - days)
        .distinct(DailyPrice.stock_id)
        .order_by(DailyPrice.stock_id, DailyPrice.date.desc())
    )
    for stock_id, close in ago_rows.all():
        latest_close, _ = out[stock_id]
        out[stock_id] = (latest_close, float(close))
    return out


async def get_close_series(
    session: AsyncSession, stock_id: int, limit: int = 200
) -> list[float]:
    """Return the most recent `limit` close prices, oldest first (for indicators)."""
    memo = memo_for(session)
    key = ("close_series", stock_id, limit)
    if memo is not None and key in memo:
        return list(memo[key])
    result = await session.execute(
        select(DailyPrice.close)
        .where(DailyPrice.stock_id == stock_id)
        .order_by(DailyPrice.date.desc())
        .limit(limit)
    )
    closes = [float(v) for v in result.scalars()]
    closes.reverse()  # chronological
    if memo is not None:
        memo[key] = list(closes)
    return closes


async def get_closes(session: AsyncSession, stock_id: int) -> list[tuple]:
    """A stock's stored (date, close) pairs, oldest first.

    Same rows, order and values as [(b.date, float(b.close)) for b in
    get_bars(...)], but reads two columns instead of every column of every
    bar: about a third of the bytes out of Neon for the valuation-history
    and risk endpoints, which only use the close (2026-11-13).
    """
    rows = await session.execute(
        select(DailyPrice.date, DailyPrice.close)
        .where(DailyPrice.stock_id == stock_id)
        .order_by(DailyPrice.date.asc())
    )
    return [(day, float(close)) for day, close in rows.all()]


@dataclass
class PerformanceInputs:
    """Everything /performance reads from a stock's bars (see get_performance_inputs)."""

    count: int = 0
    as_of: date | None = None
    last_close: Decimal | None = None
    recent: list = field(default_factory=list)  # (date, close) since as_of - 366 d, oldest first
    high_52w: Decimal | None = None
    low_52w: Decimal | None = None
    anchors: dict = field(default_factory=dict)  # window days -> (date, close) | None


async def get_performance_inputs(
    session: AsyncSession, stock_id: int, window_days, recent_days: int = 366
) -> PerformanceInputs:
    """The few values /performance needs, instead of every stored bar.

    Same answers as scanning get_bars(): the row count; the latest bar; the
    (date, close) pairs on or after latest - recent_days; that span's
    highest high and lowest low (computed by the database over the same
    stored values); and for each window, the last bar on or before
    latest - days. Before 2026-11-13 the endpoint loaded every column of
    ~2 years of bars, the largest read in the nightly stock snapshots.
    """
    base = DailyPrice.stock_id == stock_id
    count = await session.scalar(select(func.count()).select_from(DailyPrice).where(base))
    out = PerformanceInputs(count=count or 0)
    if not out.count:
        return out
    last = (
        await session.execute(
            select(DailyPrice.date, DailyPrice.close).where(base).order_by(DailyPrice.date.desc()).limit(1)
        )
    ).one()
    out.as_of, out.last_close = last.date, last.close
    cutoff = out.as_of - timedelta(days=recent_days)
    out.recent = list(
        (
            await session.execute(
                select(DailyPrice.date, DailyPrice.close)
                .where(base, DailyPrice.date >= cutoff)
                .order_by(DailyPrice.date.asc())
            )
        ).all()
    )
    hl = (
        await session.execute(
            select(func.max(DailyPrice.high), func.min(DailyPrice.low)).where(base, DailyPrice.date >= cutoff)
        )
    ).one()
    out.high_52w, out.low_52w = hl[0], hl[1]
    for days in window_days:
        target = out.as_of - timedelta(days=days)
        # Every bar on or after the cutoff is in `recent`, so if one of them
        # is on or before the target it is the last such bar overall.
        inside = [r for r in out.recent if r.date <= target]
        if inside:
            out.anchors[days] = (inside[-1].date, inside[-1].close)
            continue
        row = (
            await session.execute(
                select(DailyPrice.date, DailyPrice.close)
                .where(base, DailyPrice.date <= target)
                .order_by(DailyPrice.date.desc())
                .limit(1)
            )
        ).first()
        out.anchors[days] = (row.date, row.close) if row else None
    return out


async def get_bars(
    session: AsyncSession, stock_id: int, limit: int | None = None
) -> list[DailyPrice]:
    """Return a stock's daily bars, oldest first (chronological).

    `limit` optionally bounds the lookback to the most recent N bars.
    Used by the performance and technicals-series endpoints (Part E).
    """
    q = (
        select(DailyPrice)
        .where(DailyPrice.stock_id == stock_id)
        .order_by(DailyPrice.date.desc())
    )
    if limit is not None:
        q = q.limit(limit)
    rows = (await session.execute(q)).scalars().all()
    rows = list(rows)
    rows.reverse()  # chronological (oldest first)
    return rows