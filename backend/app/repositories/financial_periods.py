# Financial-period repository — read queries for /financials/history (Part E).
#
# The ingestion upsert lives in jobs.py, mirroring the existing pattern of
# the price/financials/news ingestions (jobs own their idempotent upserts;
# repositories own the read side).

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
