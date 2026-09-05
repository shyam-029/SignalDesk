# Alpha Score snapshot repository — get + idempotent upsert.

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AlphaScore


async def get_latest(
    session: AsyncSession, symbol: str
) -> AlphaScore | None:
    """Return the most recent alpha snapshot for a symbol (or None)."""
    return await session.scalar(
        select(AlphaScore)
        .where(AlphaScore.symbol == symbol)
        .order_by(AlphaScore.date.desc())
        .limit(1)
    )


async def get_history(
    session: AsyncSession, symbol: str, limit: int = 180
) -> list[AlphaScore]:
    """Return a symbol's alpha snapshots, oldest first (for charts).

    Bounded to the most recent `limit` snapshots before reordering.
    """
    rows = (
        await session.execute(
            select(AlphaScore)
            .where(AlphaScore.symbol == symbol)
            .order_by(AlphaScore.date.desc())
            .limit(limit)
        )
    ).scalars().all()
    return sorted(rows, key=lambda r: r.date)


async def upsert_snapshot(
    session: AsyncSession,
    symbol: str,
    snapshot_date: date,
    composite: float | None,
    fundamental: float | None,
    technical: float | None,
    sentiment: float | None,
    components_json: dict | None,
) -> None:
    """Insert or overwrite today's snapshot (idempotent by symbol+date)."""
    stmt = pg_insert(AlphaScore).values(
        symbol=symbol,
        date=snapshot_date,
        composite=composite,
        fundamental=fundamental,
        technical=technical,
        sentiment=sentiment,
        components_json=components_json,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_alpha_scores_symbol_date",
        set_={
            "composite": stmt.excluded.composite,
            "fundamental": stmt.excluded.fundamental,
            "technical": stmt.excluded.technical,
            "sentiment": stmt.excluded.sentiment,
            "components_json": stmt.excluded.components_json,
            "updated_at": func.now(),
        },
    )
    await session.execute(stmt)
    await session.commit()