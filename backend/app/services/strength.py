# Strength and steadiness ratings (pure math, no I/O).
#
# Strength answers one question: how strong has this share's price been over
# the past year, compared with the other shares on the list? The design was
# fixed in advance and tested on twelve years of NSE prices (the Alpha
# backtest research note, Part C, not yet part of this repository):
#
#   1. One-year return, skipping the latest month: the close 21 trading days
#      ago against the close 252 trading days ago.
#   2. Closeness to the one-year high: the latest close against the highest
#      close of the last 252 trading days.
#
# Each ingredient becomes a rank among the shares scored that day (best 100).
# Strength is the plain average of the two ranks, itself re-ranked. There are
# no weights to tune.
#
# Steadiness is a separate rating for the Risk card: the rank of one-year
# price swings, turned round so the calmest share scores 100.
#
# Both are ranks, so they only exist for a whole list computed in one pass.
# A share without about 13 months of closes, with a stale last bar, or with
# a one-day move too big to be real gets no score. Nothing is estimated.

from dataclasses import dataclass
from datetime import date

from app.services.depth import SUSPECT_MOVE_PCT, TRADING_DAYS

# Closes a share needs: 252 trading days back from the latest, inclusive.
HISTORY_BARS = 253
# The latest month is skipped in the one-year return.
SKIP_BARS = 21
# A last bar this many days behind the list's newest bar is stale.
STALE_DAYS = 7
# Ranking a handful of shares against each other says nothing.
MIN_RANKED = 20

REASON_SHORT_HISTORY = "short_history"
REASON_SUSPECT_MOVE = "suspect_move"
REASON_STALE = "stale"


@dataclass(frozen=True)
class PriceFacts:
    """One share's figures over its latest HISTORY_BARS closes.

    close_1m is the close SKIP_BARS trading days before the latest;
    close_12m is the oldest of the HISTORY_BARS closes. max_move and
    daily_sd are over the daily changes inside the window, as fractions.
    """

    bars: int
    last_date: date | None
    last_close: float | None
    close_1m: float | None
    close_12m: float | None
    high_1y: float | None
    max_move: float | None
    daily_sd: float | None


@dataclass(frozen=True)
class Inputs:
    year_return_pct: float
    from_high_pct: float
    volatility_pct: float | None


@dataclass(frozen=True)
class Rating:
    strength: float
    steadiness: float | None
    year_return_pct: float
    from_high_pct: float
    ranked: int


def _positive(value: float | None) -> bool:
    return value is not None and value > 0


def inputs_for(facts: PriceFacts, reference: date | None) -> tuple[Inputs | None, str | None]:
    """A share's ingredients, or the reason it has none.

    `reference` is the newest bar date on the whole list; a share whose own
    last bar is more than STALE_DAYS behind it is not ranked.
    """
    if facts.bars < HISTORY_BARS or not (
        _positive(facts.last_close)
        and _positive(facts.close_1m)
        and _positive(facts.close_12m)
        and _positive(facts.high_1y)
    ):
        return None, REASON_SHORT_HISTORY
    if facts.max_move is not None and facts.max_move * 100.0 >= SUSPECT_MOVE_PCT:
        return None, REASON_SUSPECT_MOVE
    if (
        reference is not None
        and facts.last_date is not None
        and (reference - facts.last_date).days > STALE_DAYS
    ):
        return None, REASON_STALE
    volatility = None
    if facts.daily_sd is not None and facts.daily_sd > 0:
        volatility = facts.daily_sd * (TRADING_DAYS ** 0.5) * 100.0
    return (
        Inputs(
            year_return_pct=(facts.close_1m / facts.close_12m - 1.0) * 100.0,
            from_high_pct=(facts.last_close / facts.high_1y - 1.0) * 100.0,
            volatility_pct=volatility,
        ),
        None,
    )


def percentile_ranks(values: dict[str, float]) -> dict[str, float]:
    """Rank each value among the others, 0 to 100, highest value = 100.

    Ties share the average of their places (the same rule the research
    used), so the result does not depend on input order.
    """
    n = len(values)
    if n == 0:
        return {}
    ordered = sorted(values.items(), key=lambda item: item[1])
    out: dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and ordered[j + 1][1] == ordered[i][1]:
            j += 1
        place = (i + j) / 2.0 + 1.0  # average 1-based place of the tie group
        for k in range(i, j + 1):
            out[ordered[k][0]] = place / n * 100.0
        i = j + 1
    return out


def rate_list(inputs: dict[str, Inputs]) -> dict[str, Rating]:
    """Strength and steadiness for every share that has ingredients.

    Empty when fewer than MIN_RANKED shares can be ranked.
    """
    n = len(inputs)
    if n < MIN_RANKED:
        return {}
    by_year = percentile_ranks({s: i.year_return_pct for s, i in inputs.items()})
    by_high = percentile_ranks({s: i.from_high_pct for s, i in inputs.items()})
    strength = percentile_ranks({s: (by_year[s] + by_high[s]) / 2.0 for s in inputs})
    calm = percentile_ranks(
        {s: -i.volatility_pct for s, i in inputs.items() if i.volatility_pct is not None}
    )
    return {
        s: Rating(
            strength=round(strength[s], 1),
            steadiness=round(calm[s], 1) if s in calm else None,
            year_return_pct=round(i.year_return_pct, 2),
            from_high_pct=round(i.from_high_pct, 2),
            ranked=n,
        )
        for s, i in inputs.items()
    }
