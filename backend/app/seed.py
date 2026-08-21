# One-time seeding of the Nifty 50 universe into PostgreSQL.
#
# Concept: idempotent "get-or-create". If a symbol/universe already exists we
# reuse it instead of failing or duplicating, so re-running the seed is safe.
# After seeding, the DB owns the universe; ingestion reads from the DB, not this.
#
# Note on async: we deliberately do NOT access relationship collections like
# `universe.stocks` for membership checks — that would trigger a lazy-load,
# which is forbidden in async SQLAlchemy (MissingGreenlet). Instead we query the
# association table directly (stock_universe) and append only new links.

import asyncio

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.nifty50 import NIFTY50
from app.db import SessionLocal
from app.models import Stock, Universe, stock_universe
from app.providers.yfinance_provider import MarketDataError, YFinanceProvider

UNIVERSE_NAME = "nifty50"


async def seed_universe(session: AsyncSession) -> int:
    """Create the nifty50 universe and its stock members. Returns member count."""
    # Get-or-create the universe (no relationship collection accessed).
    universe = await session.scalar(
        select(Universe).where(Universe.name == UNIVERSE_NAME)
    )
    if universe is None:
        universe = Universe(name=UNIVERSE_NAME)
        session.add(universe)
        await session.flush()  # assign universe.id

    # Load the set of stock_ids already linked to this universe, directly from
    # the association table (async-safe; avoids lazy-loading).
    linked_result = await session.execute(
        select(stock_universe.c.stock_id).where(
            stock_universe.c.universe_id == universe.id
        )
    )
    linked_stock_ids: set[int] = set(linked_result.scalars())

    added = 0
    for symbol, name, sector in NIFTY50:
        # Get-or-create the stock.
        stock = await session.scalar(select(Stock).where(Stock.symbol == symbol))
        if stock is None:
            stock = Stock(symbol=symbol, name=name, sector=sector)
            session.add(stock)
            await session.flush()  # assign stock.id

        # Link to universe only if not already linked.
        if stock.id not in linked_stock_ids:
            # Insert directly into the association table (no lazy-load needed).
            await session.execute(
                stock_universe.insert().values(
                    universe_id=universe.id, stock_id=stock.id
                )
            )
            linked_stock_ids.add(stock.id)
            added += 1

    await session.commit()
    return added


async def backfill_industry(
    provider: YFinanceProvider | None = None, batch_size: int = 5
) -> dict:
    """Populate the NULL `industry` column from the provider's stock profiles.

    Idempotent: only NULL industries are populated; existing values are kept.
    A per-symbol provider failure is isolated and logged (mirrors D19).
    """
    from sqlalchemy import select

    provider = provider or YFinanceProvider()

    async with SessionLocal() as session:
        symbols = list(
            (
                await session.execute(
                    select(Stock.symbol).where(Stock.industry.is_(None))
                )
            ).scalars()
        )

    updated = 0
    failed = 0

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        results = await asyncio.gather(
            *(provider.get_stock_profile(s) for s in batch), return_exceptions=True
        )
        for symbol, res in zip(batch, results):
            if isinstance(res, Exception):
                print(f"  industry backfill failed for {symbol}: {res}")
                failed += 1
                continue
            if res.industry is None:
                continue
            async with SessionLocal() as session:
                await session.execute(
                    update(Stock)
                    .where(Stock.symbol == symbol, Stock.industry.is_(None))
                    .values(industry=res.industry)
                )
                await session.commit()
                updated += 1

    print(f"Industry backfill done: {updated} updated, {failed} failed, {len(symbols) - updated - failed} no-industry.")
    return {"total": len(symbols), "updated": updated, "failed": failed}


async def main() -> None:
    async with SessionLocal() as session:
        linked = await seed_universe(session)
        print(f"Seeded universe '{UNIVERSE_NAME}' with {len(NIFTY50)} members (new links: {linked}).")


if __name__ == "__main__":
    asyncio.run(main())