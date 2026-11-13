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


# --- Strength on past days (alpha history, methodology v2.0) -------------------
# The same rating as the nightly pass, for every stored day at once, ranked
# inside PostgreSQL so only the requested shares' (day, value) pairs leave
# the database. Per day it ranks the shares that have a bar that day, at
# least HISTORY_BARS closes up to it, and no one-day move of
# SUSPECT_MOVE_PCT or more in the year before it; ties share the average of
# their places, as in services/strength.percentile_ranks. A day with fewer
# than MIN_RANKED such shares has no ranks. The nightly pass also drops a
# share whose last bar is a week behind the list; on a past day a share
# without a bar that day is simply not in that day's ranking.
_HISTORY_SQL = """
WITH base AS (
    SELECT s.symbol AS symbol,
           dp.date AS day,
           dp.close::float8 AS close,
           lag(dp.close::float8) OVER (PARTITION BY dp.stock_id ORDER BY dp.date) AS prev
    FROM daily_prices dp
    JOIN stocks s ON s.id = dp.stock_id
    JOIN stock_universe su ON su.stock_id = dp.stock_id
    JOIN universes u ON u.id = su.universe_id
    WHERE u.name = :universe
),
win AS (
    SELECT symbol, day, close,
           lag(close, {skip}) OVER w AS close_1m,
           lag(close, {back}) OVER w AS close_12m,
           max(close) OVER (w ROWS BETWEEN {inner} PRECEDING AND CURRENT ROW) AS high_1y,
           count(*) OVER (w ROWS BETWEEN {back} PRECEDING AND CURRENT ROW) AS n,
           max(CASE WHEN prev > 0 THEN abs(close / prev - 1.0) END)
               OVER (w ROWS BETWEEN {inner} PRECEDING AND CURRENT ROW) AS max_move
    FROM base
    WINDOW w AS (PARTITION BY symbol ORDER BY day)
),
eligible AS (
    SELECT symbol, day,
           close_1m / close_12m - 1.0 AS yr,
           close / high_1y - 1.0 AS fh
    FROM win
    WHERE n = {history} AND day >= :since
      AND close > 0 AND close_1m > 0 AND close_12m > 0 AND high_1y > 0
      AND coalesce(max_move, 0) * 100.0 < :suspect
),
ranked AS (
    SELECT symbol, day,
           count(*) OVER (PARTITION BY day) AS n_day,
           (rank() OVER (PARTITION BY day ORDER BY yr)
              + (count(*) OVER (PARTITION BY day, yr) - 1) / 2.0) AS p_yr,
           (rank() OVER (PARTITION BY day ORDER BY fh)
              + (count(*) OVER (PARTITION BY day, fh) - 1) / 2.0) AS p_fh
    FROM eligible
),
mixed AS (
    -- The sum of the two places orders shares exactly as the average of the
    -- two ranks does, and is exact (services/strength.rate_list).
    SELECT symbol, day, n_day, p_yr + p_fh AS mix
    FROM ranked
    WHERE n_day >= :min_ranked
),
final AS (
    SELECT symbol, day,
           (rank() OVER (PARTITION BY day ORDER BY mix)
              + (count(*) OVER (PARTITION BY day, mix) - 1) / 2.0) / n_day * 100.0 AS strength
    FROM mixed
)
SELECT symbol, day, strength FROM final
{only}
"""


async def get_strength_history(
    session: AsyncSession,
    universe_name: str,
    since: date,
    symbols: list[str] | None = None,
) -> dict[str, dict[date, float]]:
    """Strength rank (0-100, one decimal) per share per stored day since `since`.

    Ranks are always taken over the whole list; `symbols` only limits which
    shares' values are returned (and so the bytes moved).
    """
    from app.services.depth import SUSPECT_MOVE_PCT
    from app.services.strength import MIN_RANKED

    only = "WHERE symbol = ANY(:symbols)" if symbols is not None else ""
    sql = _HISTORY_SQL.format(
        skip=SKIP_BARS,
        back=HISTORY_BARS - 1,
        inner=HISTORY_BARS - 2,
        history=HISTORY_BARS,
        only=only,
    )
    params: dict = {
        "universe": universe_name,
        "since": since,
        "suspect": float(SUSPECT_MOVE_PCT),
        "min_ranked": MIN_RANKED,
    }
    if symbols is not None:
        if not symbols:
            return {}
        params["symbols"] = list(symbols)
    out: dict[str, dict[date, float]] = {}
    for r in (await session.execute(text(sql), params)).all():
        out.setdefault(r.symbol, {})[r.day] = round(float(r.strength), 1)
    return out


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


_UPDATE_COMPOSITE_SQL = text(
    """
    UPDATE alpha_scores
    SET composite = :composite, updated_at = now()
    WHERE symbol = :symbol AND date = :day
      AND composite IS DISTINCT FROM CAST(:composite AS numeric)
    """
)


async def recompose_composites(
    session: AsyncSession, pairs: list[tuple[str, date]]
) -> int:
    """Re-blend the composite of each (symbol, day) row from its stored pillars.

    Uses the row's own fundamental and sentiment columns and its stored
    Strength (methodology v2.0, services/alpha._renormalized). Reads only
    those small columns and rewrites only rows whose composite changes.
    Live rows only: a row with neither a fundamental nor a sentiment value
    is a backfilled history row, left to backfill_alpha_history. Commits
    once; returns the number of rows changed.
    """
    from app.services.alpha import _renormalized

    if not pairs:
        return 0
    wanted = set(pairs)
    rows = (
        await session.execute(
            select(
                AlphaScore.symbol,
                AlphaScore.date,
                AlphaScore.fundamental,
                AlphaScore.sentiment,
                AlphaScore.composite,
                AlphaScore.components_json[KEY_STRENGTH].astext.label("strength"),
            ).where(
                AlphaScore.symbol.in_({s for s, _ in pairs}),
                AlphaScore.date.in_({d for _, d in pairs}),
            )
        )
    ).all()
    changed = 0
    for r in rows:
        if (r.symbol, r.date) not in wanted:
            continue
        if r.fundamental is None and r.sentiment is None:
            # A backfilled history row: its composite blends today's
            # fundamental and sentiment and is owned by the history job.
            continue
        strength = round(float(r.strength)) if r.strength is not None else None
        composite, _ = _renormalized(
            float(r.fundamental) if r.fundamental is not None else None,
            strength,
            float(r.sentiment) if r.sentiment is not None else None,
        )
        current = float(r.composite) if r.composite is not None else None
        if composite == current:
            continue
        await session.execute(
            _UPDATE_COMPOSITE_SQL,
            {"symbol": r.symbol, "day": r.date, "composite": composite},
        )
        changed += 1
    await session.commit()
    return changed


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
