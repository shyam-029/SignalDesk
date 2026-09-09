# Financial-period repository — read queries for /financials/history (Part E).
#
# The ingestion upsert lives in jobs.py, mirroring the existing pattern of
# the price/financials/news ingestions (jobs own their idempotent upserts;
# repositories own the read side).

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FinancialPeriod


async def get_periods(
    session: AsyncSession,
    stock_id: int,
    period_type: str | None = None,
) -> list[FinancialPeriod]:
    """Return a stock's historical periods, newest period end first.

    period_type filters to "annual" or "quarterly" when given; None returns
    every stored period.
    """
    q = (
        select(FinancialPeriod)
        .where(FinancialPeriod.stock_id == stock_id)
        .order_by(FinancialPeriod.period_end.desc())
    )
    if period_type is not None:
        q = q.where(FinancialPeriod.period_type == period_type)
    result = await session.execute(q)
    return list(result.scalars())


async def get_annual_revenue(
    session: AsyncSession, stock_ids: list[int]
) -> dict[int, list[tuple[date, float]]]:
    """Batched annual revenue series for growth math (M2-T8 enriched peers).

    {stock_id: [(period_end, revenue), ...]} ordered period_end ASC. Only
    periods that actually carry a revenue contribute: a missing value is
    never zero-filled into a series (that would fabricate a collapse).
    """
    if not stock_ids:
        return {}
    q = (
        select(FinancialPeriod)
        .where(
            FinancialPeriod.stock_id.in_(stock_ids),
            FinancialPeriod.period_type == "annual",
            FinancialPeriod.revenue.is_not(None),
        )
        .order_by(FinancialPeriod.stock_id.asc(), FinancialPeriod.period_end.asc())
    )
    rows = (await session.execute(q)).scalars().all()
    out: dict[int, list[tuple[date, float]]] = {}
    for row in rows:
        out.setdefault(row.stock_id, []).append(
            (row.period_end, float(row.revenue))
        )
    return out
