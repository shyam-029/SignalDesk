# Price repository — batched lookups to avoid N+1 queries.
#
# list_stocks previously ran 2 queries per stock. get_two_latest runs ONE query
# with a window function (ROW_NUMBER partitioned by stock) to fetch the latest
# two price rows for many stocks at once.

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.models import DailyPrice


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


async def get_close_series(
    session: AsyncSession, stock_id: int, limit: int = 200
) -> list[float]:
    """Return the most recent `limit` close prices, oldest first (for indicators)."""
    result = await session.execute(
        select(DailyPrice.close)
        .where(DailyPrice.stock_id == stock_id)
        .order_by(DailyPrice.date.desc())
        .limit(limit)
    )
    closes = [float(v) for v in result.scalars()]
    closes.reverse()  # chronological
    return closes


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