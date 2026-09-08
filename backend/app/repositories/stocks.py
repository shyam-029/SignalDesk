# Stock repository — lookups for the catalog and peer selection.
#
# New concept: repository layer. SQL lives ONLY here; routers/services never
# write SQL. Functions take an AsyncSession (injected by the router).

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Stock, Universe, stock_universe


def active_universe_filter(stmt):
    """Constrain a Stock query to the ACTIVE ranked universe (top 1000).

    The catalog holds more rows than the ranked universe (D18 keeps peer
    selection universe-independent); the research surfaces (list, screener,
    search) present the ranked 1000 the user navigates. Rows outside the
    universe stay reachable by direct URL.
    """
    return stmt.where(
        Stock.id.in_(
            select(stock_universe.c.stock_id)
            .join(Universe, Universe.id == stock_universe.c.universe_id)
            .where(Universe.name == settings.active_universe)
        )
    )


async def get_stock(session: AsyncSession, symbol: str) -> Stock | None:
    """Return a stock by its (already-normalized) symbol, or None.

    Deliberately NOT universe-scoped: any catalog row keeps its research
    page reachable by direct URL.
    """
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


async def search_universe(
    session: AsyncSession, query: str, limit: int = 10
) -> list[Stock]:
    """Server-side search over the active universe by symbol or company name.

    Case-insensitive substring match; symbol-prefix matches first, then
    name matches, each alphabetical. Replaces the old client-side filter
    over the first catalog page, which could only ever see 250 of 2,900
    rows (ETERNAL/SWIGGY/IFCI were ranked-in and invisible).
    """
    q = f"%{query.strip().upper()}%"
    bare = query.strip().upper()
    stmt = (
        select(Stock)
        .where(
            Stock.is_etf.is_(False),
            (Stock.symbol.ilike(q)) | (Stock.name.ilike(q)),
        )
    )
    stmt = active_universe_filter(stmt)
    rows = (await session.execute(stmt)).scalars().all()

    def _rank(s: Stock) -> tuple[int, str]:
        sym = s.symbol.upper()
        name = (s.name or "").upper()
        if sym.startswith(bare) or sym.split(".")[0].startswith(bare):
            return (0, sym)
        if name.startswith(bare):
            return (1, sym)
        return (2, sym)

    rows.sort(key=_rank)
    return rows[:limit]


async def list_all_symbols(session: AsyncSession) -> list[str]:
    """Return every EQUITY symbol in the ACTIVE universe (used by the screener).

    ETFs (is_etf) are a separate domain (Plan 9, GET /etfs) and never enter
    the equity screener; the screener also presents the ranked top-1000, not
    the full catalog.
    """
    stmt = select(Stock.symbol).where(Stock.is_etf.is_(False))
    stmt = active_universe_filter(stmt)
    result = await session.execute(stmt.order_by(Stock.symbol))
    return list(result.scalars())