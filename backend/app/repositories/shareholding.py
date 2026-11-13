# Shareholding repository (checklist 6, step 3).
#
# One row per stock per quarter end. The upsert anchors on
# (stock_id, period_end) so reruns stay idempotent, COALESCEs each category
# so a sparse provider response never blanks a stored figure, and skips rows
# whose values are unchanged (upsert_guard) so re-offering the same quarters
# writes nothing.

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ShareholdingPeriod, Stock, Universe, stock_universe
from app.providers.base import SHAREHOLDING_CATEGORIES, ShareholdingDraft
from app.repositories.upsert_guard import any_distinct


async def table_exists(session: AsyncSession) -> bool:
    """True once the shareholding_periods migration has been applied.

    Migrations are run by hand, not on deploy, so code can reach production
    before the table does. Callers use this to report "no data yet" instead
    of failing.
    """
    found = await session.scalar(
        text("SELECT to_regclass('shareholding_periods') IS NOT NULL")
    )
    return bool(found)


async def upsert_periods(
    session: AsyncSession, stock_id: int, drafts: list[ShareholdingDraft]
) -> int:
    """Bulk-upsert one stock's quarters; returns the number of rows offered."""
    if not drafts:
        return 0
    rows = [
        {
            "stock_id": stock_id,
            "period_end": d.period_end,
            **{c: getattr(d, c) for c in SHAREHOLDING_CATEGORIES},
            "source": d.source or "unknown",
        }
        for d in drafts
    ]
    stmt = pg_insert(ShareholdingPeriod).values(rows)
    new_values = {
        c: func.coalesce(getattr(stmt.excluded, c), getattr(ShareholdingPeriod, c))
        for c in SHAREHOLDING_CATEGORIES
    }
    stmt = stmt.on_conflict_do_update(
        constraint="uq_shareholding_periods_stock_period",
        set_={**new_values, "source": stmt.excluded.source, "ingested_at": func.now()},
        where=any_distinct(ShareholdingPeriod, new_values),
    )
    await session.execute(stmt)
    await session.commit()
    return len(rows)


async def get_periods(
    session: AsyncSession, stock_id: int
) -> list[ShareholdingPeriod]:
    """A stock's stored quarters, oldest first."""
    rows = await session.execute(
        select(ShareholdingPeriod)
        .where(ShareholdingPeriod.stock_id == stock_id)
        .order_by(ShareholdingPeriod.period_end.asc())
    )
    return list(rows.scalars())


async def get_universe_coverage(
    session: AsyncSession, universe: str
) -> list[tuple[str, object]]:
    """[(symbol, latest stored quarter end | None)] for a universe, by symbol.

    The nightly pass decides from this which stocks are due a refresh.
    """
    latest = (
        select(
            ShareholdingPeriod.stock_id.label("stock_id"),
            func.max(ShareholdingPeriod.period_end).label("latest"),
        )
        .group_by(ShareholdingPeriod.stock_id)
        .subquery()
    )
    rows = await session.execute(
        select(Stock.symbol, latest.c.latest)
        .join(stock_universe, stock_universe.c.stock_id == Stock.id)
        .join(Universe, Universe.id == stock_universe.c.universe_id)
        .outerjoin(latest, latest.c.stock_id == Stock.id)
        .where(Universe.name == universe)
        .order_by(Stock.symbol.asc())
    )
    return [(symbol, day) for symbol, day in rows.all()]
