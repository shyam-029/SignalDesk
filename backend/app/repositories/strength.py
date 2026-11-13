# Strength rating repository.
#
# Reads: one aggregate query turns each share's latest 253 closes into a
# single row of figures inside PostgreSQL, so the nightly pass moves about a
# thousand small rows out of the database instead of a quarter of a million
# closes (network transfer is metered).
#
# Writes: the ratings are merged into the day's alpha_scores row under their
# own keys in components_json. No new table, so no migration. Every stored
# value is a number, because the alpha history endpoint returns that column
# as it is.

import json
from datetime import date, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AlphaScore
from app.services.strength import HISTORY_BARS, SKIP_BARS, PriceFacts

# Calendar days read back to find 253 trading days (about 365), with slack
# for holidays. A share halted for longer than the slack shows no score.
LOOKBACK_DAYS = 420

KEY_STRENGTH = "strength"
KEY_STEADINESS = "steadiness"
# Only the two ranks are stored: they cannot be recomputed for one share.
# The year's return and the gap to the high are worked out from the share's
# own prices when the endpoint is read, so they cost no storage (the rows
# accumulate as history, about 1,000 a night).
RATING_KEYS = (KEY_STRENGTH, KEY_STEADINESS)

_FACTS_SQL = """
WITH recent AS (
    SELECT s.symbol AS symbol,
           dp.date AS day,
           dp.close::float8 AS close,
           row_number() OVER (PARTITION BY dp.stock_id ORDER BY dp.date DESC) AS rn,
           lag(dp.close::float8) OVER (PARTITION BY dp.stock_id ORDER BY dp.date) AS prev
    FROM daily_prices dp
    JOIN stocks s ON s.id = dp.stock_id
    {scope_join}
    WHERE dp.date >= :since {scope_where}
)
SELECT symbol,
       count(*) AS bars,
       max(day) AS last_date,
       max(close) FILTER (WHERE rn = 1) AS last_close,
       max(close) FILTER (WHERE rn = :skip_rn) AS close_1m,
       max(close) FILTER (WHERE rn = :history) AS close_12m,
       max(close) FILTER (WHERE rn < :history) AS high_1y,
       max(abs(close / prev - 1.0)) FILTER (WHERE rn < :history AND prev > 0) AS max_move,
       stddev_samp(close / prev - 1.0) FILTER (WHERE rn < :history AND prev > 0) AS daily_sd
FROM recent
WHERE rn <= :history
GROUP BY symbol
"""

_UNIVERSE_JOIN = (
    "JOIN stock_universe su ON su.stock_id = dp.stock_id "
    "JOIN universes u ON u.id = su.universe_id"
)


async def get_price_facts(
    session: AsyncSession,
    today: date,
    universe_name: str | None = None,
    stock_id: int | None = None,
) -> dict[str, PriceFacts]:
    """Figures over each share's latest 253 closes, keyed by symbol.

    Pass `universe_name` for a whole list or `stock_id` for one share. A
    share with no bar inside the lookback is absent from the result.
    """
    params: dict = {
        "since": today - timedelta(days=LOOKBACK_DAYS),
        "skip_rn": SKIP_BARS + 1,
        "history": HISTORY_BARS,
    }
    scope_join, scope_where = "", ""
    if stock_id is not None:
        scope_where = "AND dp.stock_id = :stock_id"
        params["stock_id"] = stock_id
    elif universe_name is not None:
        scope_join = _UNIVERSE_JOIN
        scope_where = "AND u.name = :universe"
        params["universe"] = universe_name
    sql = _FACTS_SQL.format(scope_join=scope_join, scope_where=scope_where)
    rows = (await session.execute(text(sql), params)).all()
    return {
        r.symbol: PriceFacts(
            bars=int(r.bars),
            last_date=r.last_date,
            last_close=r.last_close,
            close_1m=r.close_1m,
            close_12m=r.close_12m,
            high_1y=r.high_1y,
            max_move=r.max_move,
            daily_sd=r.daily_sd,
        )
        for r in rows
    }


_MERGE_SQL = text(
    """
    UPDATE alpha_scores
    SET components_json = coalesce(components_json, '{}'::jsonb) || CAST(:patch AS jsonb),
        updated_at = now()
    WHERE symbol = :symbol
      AND date = :day
      AND NOT (coalesce(components_json, '{}'::jsonb) @> CAST(:patch AS jsonb))
    """
)

_CLEAR_SQL = text(
    """
    UPDATE alpha_scores
    SET components_json = components_json - CAST(:keys AS text[]),
        updated_at = now()
    WHERE symbol = :symbol
      AND date = :day
      AND components_json ?| CAST(:keys AS text[])
    """
)


async def store_ratings(
    session: AsyncSession,
    rated: list[tuple[str, date, dict[str, float]]],
    unrated: list[tuple[str, date]],
) -> dict[str, int]:
    """Merge ratings into each share's alpha row for its latest bar date.

    A share with no alpha row for that date is skipped (it is counted in
    neither figure). Rows that already hold the same values are not
    rewritten. Shares that could not be rated have any rating keys removed
    from that day's row, so a re-run never leaves a stale score behind.
    Commits once.
    """
    written = 0
    for symbol, day, patch in rated:
        result = await session.execute(
            _MERGE_SQL, {"symbol": symbol, "day": day, "patch": json.dumps(patch)}
        )
        written += result.rowcount or 0
    cleared = 0
    for symbol, day in unrated:
        result = await session.execute(
            _CLEAR_SQL, {"symbol": symbol, "day": day, "keys": list(RATING_KEYS)}
        )
        cleared += result.rowcount or 0
    await session.commit()
    return {"written": written, "cleared": cleared}


async def get_latest_rating(
    session: AsyncSession, symbol: str
) -> tuple[date, dict[str, float]] | None:
    """The newest stored rating for a symbol: (snapshot date, values)."""
    row = (
        await session.execute(
            select(AlphaScore.date, AlphaScore.components_json)
            .where(
                AlphaScore.symbol == symbol,
                AlphaScore.components_json.has_key(KEY_STRENGTH),  # noqa: W601
            )
            .order_by(AlphaScore.date.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    values = {k: row.components_json[k] for k in RATING_KEYS if k in row.components_json}
    return row.date, values
