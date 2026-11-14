# Reads and writes for the edge features (track record, similar setups,
# what the price assumes). See services/setups.py and services/expectations.py
# for the math.

import time
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EdgeSnapshot, FinancialPeriod, PickList

UNIVERSE_NAME = "top1000"
PICKS_PER_LIST = 20
RATINGS = ("alpha", "strength")

# --- Snapshots -------------------------------------------------------------

SNAPSHOT_CHUNK = 200


async def upsert_snapshots(
    session: AsyncSession, rows: list[tuple[str, date, dict]]
) -> int:
    """Write (key, asof, payload) rows; a row whose payload is unchanged is
    left alone. Commits once; returns the number of rows written."""
    written = 0
    for start in range(0, len(rows), SNAPSHOT_CHUNK):
        chunk = rows[start : start + SNAPSHOT_CHUNK]
        stmt = pg_insert(EdgeSnapshot).values(
            [{"key": k, "asof": a, "payload": p} for k, a, p in chunk]
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_edge_snapshots_key",
            set_={
                "asof": stmt.excluded.asof,
                "payload": stmt.excluded.payload,
                "updated_at": text("now()"),
            },
            where=EdgeSnapshot.payload.is_distinct_from(stmt.excluded.payload),
        )
        result = await session.execute(stmt)
        written += result.rowcount or 0
    await session.commit()
    return written


async def get_snapshot(session: AsyncSession, key: str) -> EdgeSnapshot | None:
    return (
        await session.execute(select(EdgeSnapshot).where(EdgeSnapshot.key == key))
    ).scalar_one_or_none()


def setups_key(symbol: str) -> str:
    return f"setups:{symbol}"


SETUPS_BASELINE_KEY = "setups_baseline"
STRENGTH_BACKTEST_KEY = "strength_backtest"

# --- Base rates for "what the price assumes" ---------------------------------

_BASE_ROWS_TTL_S = 12 * 3600
_base_rows: tuple[float, list] | None = None


async def get_annual_growth_rows(
    session: AsyncSession,
) -> list[tuple[int, date, float | None, float | None]]:
    """Every stored annual (stock id, period end, net income, revenue).

    About 4,600 small rows, read at most twice a day per process.
    """
    global _base_rows
    now = time.monotonic()
    if _base_rows is not None and now - _base_rows[0] < _BASE_ROWS_TTL_S:
        return _base_rows[1]
    rows = (
        await session.execute(
            select(
                FinancialPeriod.stock_id,
                FinancialPeriod.period_end,
                FinancialPeriod.net_income,
                FinancialPeriod.revenue,
            ).where(FinancialPeriod.period_type == "annual")
        )
    ).all()
    out = [
        (
            r.stock_id,
            r.period_end,
            float(r.net_income) if r.net_income is not None else None,
            float(r.revenue) if r.revenue is not None else None,
        )
        for r in rows
    ]
    _base_rows = (now, out)
    return out


def reset_cache() -> None:
    global _base_rows, _track_cache
    _base_rows = None
    _track_cache = None


# --- Frozen pick lists -------------------------------------------------------

_LATEST_LIVE_DAY_SQL = text(
    """
    SELECT max(date) FROM alpha_scores
    WHERE composite IS NOT NULL AND fundamental IS NOT NULL
    """
)

_TOP_SQL = """
    SELECT a.symbol, {score} AS score, dp.close::float8 AS close
    FROM alpha_scores a
    JOIN stocks s ON s.symbol = a.symbol
    JOIN stock_universe su ON su.stock_id = s.id
    JOIN universes u ON u.id = su.universe_id AND u.name = :universe
    LEFT JOIN daily_prices dp ON dp.stock_id = s.id AND dp.date = a.date
    WHERE a.date = :day AND {score} IS NOT NULL
    ORDER BY {score} DESC, a.symbol
    LIMIT :n
"""

_SCORES = {
    "alpha": "a.composite::float8",
    "strength": "(a.components_json->>'strength')::float8",
}


async def latest_live_day(session: AsyncSession) -> date | None:
    return (await session.execute(_LATEST_LIVE_DAY_SQL)).scalar()


async def has_list_in_month(session: AsyncSession, day: date) -> bool:
    first = day.replace(day=1)
    found = (
        await session.execute(
            select(PickList.id).where(PickList.list_date >= first).limit(1)
        )
    ).first()
    return found is not None


async def freeze_lists(session: AsyncSession, day: date) -> dict[str, int]:
    """Write each rating's top PICKS_PER_LIST for `day`. Commits once.

    Rows are only ever inserted (an existing row for the same date, rating
    and share is left exactly as it was).
    """
    counts: dict[str, int] = {}
    for rating in RATINGS:
        rows = (
            await session.execute(
                text(_TOP_SQL.format(score=_SCORES[rating])),
                {"day": day, "universe": UNIVERSE_NAME, "n": PICKS_PER_LIST},
            )
        ).all()
        if not rows:
            counts[rating] = 0
            continue
        stmt = pg_insert(PickList).values(
            [
                {
                    "list_date": day,
                    "rating": rating,
                    "rank": i + 1,
                    "symbol": r.symbol,
                    "score": round(r.score, 2),
                    "entry_close": r.close,
                }
                for i, r in enumerate(rows)
            ]
        ).on_conflict_do_nothing(constraint="uq_pick_lists_date_rating_symbol")
        result = await session.execute(stmt)
        counts[rating] = result.rowcount or 0
    await session.commit()
    return counts


# Each pick's first close after its list date (the entry) and its latest close.
_PICK_RETURNS_SQL = text(
    """
    SELECT p.list_date, p.rating, p.rank, p.symbol, p.score,
           s.name,
           e.date AS entry_date, e.close::float8 AS entry_close,
           l.date AS last_date, l.close::float8 AS last_close
    FROM pick_lists p
    LEFT JOIN stocks s ON s.symbol = p.symbol
    LEFT JOIN LATERAL (
        SELECT date, close FROM daily_prices
        WHERE stock_id = s.id AND date > p.list_date
        ORDER BY date LIMIT 1
    ) e ON true
    LEFT JOIN LATERAL (
        SELECT date, close FROM daily_prices
        WHERE stock_id = s.id ORDER BY date DESC LIMIT 1
    ) l ON true
    ORDER BY p.list_date DESC, p.rating, p.rank
    """
)

# The average share on the list over the same days, for each list date.
_LIST_AVERAGE_SQL = text(
    """
    WITH lists AS (SELECT DISTINCT list_date FROM pick_lists),
    members AS (
        SELECT s.id FROM stocks s
        JOIN stock_universe su ON su.stock_id = s.id
        JOIN universes u ON u.id = su.universe_id AND u.name = :universe
    ),
    latest AS (
        SELECT DISTINCT ON (dp.stock_id) dp.stock_id, dp.close::float8 AS close
        FROM daily_prices dp JOIN members m ON m.id = dp.stock_id
        ORDER BY dp.stock_id, dp.date DESC
    )
    SELECT l.list_date,
           avg(lt.close / e.close - 1.0) AS avg_return,
           count(*) AS shares
    FROM lists l
    CROSS JOIN members m
    JOIN LATERAL (
        SELECT close::float8 AS close FROM daily_prices
        WHERE stock_id = m.id AND date > l.list_date
        ORDER BY date LIMIT 1
    ) e ON true
    JOIN latest lt ON lt.stock_id = m.id
    WHERE e.close > 0
    GROUP BY l.list_date
    """
)

_INDEX_RETURN_SQL = text(
    """
    WITH lists AS (SELECT DISTINCT list_date FROM pick_lists),
    b AS (SELECT id FROM benchmarks WHERE symbol = :index),
    latest AS (
        SELECT bp.close::float8 AS close FROM benchmark_prices bp, b
        WHERE bp.benchmark_id = b.id ORDER BY bp.date DESC LIMIT 1
    )
    SELECT l.list_date, (SELECT close FROM latest) / e.close - 1.0 AS ret
    FROM lists l
    JOIN LATERAL (
        SELECT bp.close::float8 AS close FROM benchmark_prices bp, b
        WHERE bp.benchmark_id = b.id AND bp.date > l.list_date
        ORDER BY bp.date LIMIT 1
    ) e ON true
    """
)

_TRACK_TTL_S = 3600
_track_cache: tuple[float, dict] | None = None


async def get_track_record_rows(session: AsyncSession) -> dict:
    """Pick rows with entry and latest closes, the list average and the
    NIFTY 50 for every list date. Cached for an hour per process."""
    global _track_cache
    now = time.monotonic()
    if _track_cache is not None and now - _track_cache[0] < _TRACK_TTL_S:
        return _track_cache[1]
    picks = (await session.execute(_PICK_RETURNS_SQL)).all()
    averages = {
        r.list_date: (r.avg_return, r.shares)
        for r in (await session.execute(_LIST_AVERAGE_SQL, {"universe": UNIVERSE_NAME})).all()
    }
    index = {
        r.list_date: r.ret
        for r in (await session.execute(_INDEX_RETURN_SQL, {"index": "^NSEI"})).all()
    }
    out = {"picks": picks, "averages": averages, "index": index}
    _track_cache = (now, out)
    return out
