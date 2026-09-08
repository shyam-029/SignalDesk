# Stock repository — lookups for the catalog and peer selection.
#
# New concept: repository layer. SQL lives ONLY here; routers/services never
# write SQL. Functions take an AsyncSession (injected by the router).

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Stock


async def get_stock(session: AsyncSession, symbol: str) -> Stock | None:
    """Return a stock by its (already-normalized) symbol, or None."""
    return await session.scalar(select(Stock).where(Stock.symbol == symbol))


async def get_peers(session: AsyncSession, stock: Stock) -> list[Stock]:
    """Return same-industry peers (excluding the stock itself).

    Peer classification: use `industry` when the target has one; otherwise fall
    back to `sector` (defensive — a few stocks lack industry after backfill).

    Unclassified stocks (industry AND sector both NULL — ranking-created
    catalog rows never enriched) have NO peer set: an `IS NULL` match would
    group thousands of unrelated companies into one meaningless peer set
    (M1-T3 500: UTIAMC.NS matched 2,655 "peers", fanning one /alpha request
    into thousands of provider calls). Empty list, never the NULL cohort.
    """
    if stock.industry is not None:
        column, classifier = Stock.industry, stock.industry
    elif stock.sector is not None:
        column, classifier = Stock.sector, stock.sector
    else:
        return []

    q = select(Stock).where(column == classifier, Stock.id != stock.id)
    result = await session.execute(q)
    return list(result.scalars())


async def list_all_symbols(session: AsyncSession) -> list[str]:
    """Return every symbol in the catalog (used by the screener)."""
    result = await session.execute(select(Stock.symbol).order_by(Stock.symbol))
    return list(result.scalars())