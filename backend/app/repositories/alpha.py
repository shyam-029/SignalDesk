# Alpha Score snapshot repository — get + idempotent upsert.

from datetime import date

from sqlalchemy import and_, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AlphaScore
from app.repositories.upsert_guard import INSERTED_FLAG, any_distinct


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


_SNAPSHOT_COLUMNS = ("composite", "fundamental", "technical", "sentiment", "components_json")

# asyncpg caps a statement at 32767 bind parameters; 6 per row here.
_SYNC_CHUNK_ROWS = 2000


async def sync_backfill_snapshots(
    session: AsyncSession, symbol: str, rows: list[dict]
) -> dict[str, int]:
    """Make a symbol's technical-only snapshots equal `rows`, in ONE transaction.

    Replaces the old wipe-then-insert (two transactions), which deleted and
    re-inserted every backfilled row every night: ~493k dead rows per run,
    unbounded primary-key index bloat (measured 93.8 MB for 507k rows), and a
    window where the symbol had no history at all. The end state is the same:

      - each row in `rows` is inserted, or updated when its values changed;
        unchanged rows are not written at all (no-op guard);
      - a stored LIVE snapshot (fundamental IS NOT NULL) on the same date is
        never overwritten (the guard requires the stored fundamental is NULL);
      - stored technical-only rows whose date is not in `rows` are deleted
        (the series is recomputed under the current formula; stale dates
        must not survive).

    Commits once at the end, so readers see either the old or the new series.
    Returns {"inserted", "updated", "unchanged", "deleted"}.
    """
    counts = {"inserted": 0, "updated": 0, "unchanged": 0, "deleted": 0}
    if not rows:
        return counts

    for start in range(0, len(rows), _SYNC_CHUNK_ROWS):
        chunk = rows[start : start + _SYNC_CHUNK_ROWS]
        stmt = pg_insert(AlphaScore).values(chunk)
        new_values = {col: getattr(stmt.excluded, col) for col in _SNAPSHOT_COLUMNS}
        stmt = stmt.on_conflict_do_update(
            constraint="uq_alpha_scores_symbol_date",
            set_={**new_values, "updated_at": func.now()},
            where=and_(
                AlphaScore.fundamental.is_(None),
                any_distinct(AlphaScore, new_values),
            ),
        ).returning(INSERTED_FLAG)
        flags = list((await session.execute(stmt)).scalars())
        inserted = sum(1 for f in flags if f)
        counts["inserted"] += inserted
        counts["updated"] += len(flags) - inserted
        # Skipped = unchanged rows AND rows blocked by a live snapshot.
        counts["unchanged"] += len(chunk) - len(flags)

    keep_dates = [r["date"] for r in rows]
    result = await session.execute(
        delete(AlphaScore).where(
            AlphaScore.symbol == symbol,
            AlphaScore.fundamental.is_(None),
            AlphaScore.date.not_in(keep_dates),
        )
    )
    counts["deleted"] = result.rowcount or 0
    await session.commit()
    return counts