# Balance-sheet repository — persistence for Plan 5.4 snapshots.
#
# The Altman Z-Score (services/altman.py) reads the latest annual row from
# here. Upserts anchor on (stock_id, period_end, period_type) so reruns stay
# idempotent, mirroring financial_periods.

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BalanceSheetPeriod
from app.providers.base import BalanceSheetDraft


async def upsert_periods(
    session: AsyncSession, stock_id: int, drafts: list[BalanceSheetDraft]
) -> int:
    """Bulk-upsert one stock's balance-sheet periods; rows offered returned."""
    if not drafts:
        return 0
    rows = [
        {
            "stock_id": stock_id,
            "period_end": d.period_end,
            "period_type": d.period_type,
            "working_capital": d.working_capital,
            "total_assets": d.total_assets,
            "retained_earnings": d.retained_earnings,
            "ebit": d.ebit,
            "book_equity": d.book_equity,
            "total_liabilities": d.total_liabilities,
            "source": d.source or "unknown",
        }
        for d in drafts
    ]
    stmt = pg_insert(BalanceSheetPeriod).values(rows)
    # Field-level COALESCE on conflict (incident 2026-09-09): a sparse
    # provider response must keep previously-good stored figures instead of
    # nulling them; only columns the provider actually supplied change.
    stmt = stmt.on_conflict_do_update(
        constraint="uq_balance_sheet_periods_stock_period",
        set_={
            "working_capital": func.coalesce(stmt.excluded.working_capital, BalanceSheetPeriod.working_capital),
            "total_assets": func.coalesce(stmt.excluded.total_assets, BalanceSheetPeriod.total_assets),
            "retained_earnings": func.coalesce(stmt.excluded.retained_earnings, BalanceSheetPeriod.retained_earnings),
            "ebit": func.coalesce(stmt.excluded.ebit, BalanceSheetPeriod.ebit),
            "book_equity": func.coalesce(stmt.excluded.book_equity, BalanceSheetPeriod.book_equity),
            "total_liabilities": func.coalesce(stmt.excluded.total_liabilities, BalanceSheetPeriod.total_liabilities),
            "source": stmt.excluded.source,
            "ingested_at": func.now(),
        },
    )
    await session.execute(stmt)
    await session.commit()
    return len(rows)


async def get_latest(
    session: AsyncSession, stock_id: int
) -> BalanceSheetPeriod | None:
    """The most recent annual balance-sheet row for a stock (or None)."""
    return await session.scalar(
        select(BalanceSheetPeriod)
        .where(BalanceSheetPeriod.stock_id == stock_id)
        .order_by(BalanceSheetPeriod.period_end.desc())
        .limit(1)
    )
