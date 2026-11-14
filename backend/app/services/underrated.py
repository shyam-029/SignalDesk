# The "underrated" scan (owner request, 2026-11-14). Pure logic, no I/O.
#
# Strength finds what has already risen, so by the time a stock is on that
# list part of the move is behind it. This scan looks for the opposite:
# companies in good shape whose price assumes little and which the market has
# not yet re-rated. Four checks, every number shown to the reader:
#
#   1. Good business: Fundamental score at least 70 (the list's upper
#      half) and a Solvency score of at least 50 (no stretched balance sheet).
#   2. Price assumes little: the yearly earnings growth today's market value
#      needs for ten years (services/expectations, at 12%) is at most 10%, and
#      the company's own recent earnings growth is at least 5 points above it.
#   3. Cheap against peers: the peer-relative valuation reads undervalued
#      (the stock's own-history band is on its Valuation section; 12 years of
#      statements are not stored, so it is not part of this test).
#   4. Not yet re-rated: Strength at most 60 and the price at least 10% below
#      its one-year high.
#
# A stock that passes all four is a "match"; three of four is a "near miss".
# This is a research screen, untested as a strategy: the frozen monthly list
# on the track-record page is its test. Cheap companies can be cheap for a
# reason; every figure behind each check is returned so it can be read.

from dataclasses import dataclass

from app.services import expectations as exp

MIN_FUNDAMENTAL = 70.0
MIN_SOLVENCY = 50.0
MAX_NEEDED_GROWTH_PCT = 10.0
MIN_GROWTH_GAP_POINTS = 5.0
MAX_STRENGTH = 60.0
MIN_BELOW_HIGH_PCT = 10.0
# Growth above this comes from a tiny starting profit (a recovery from near
# zero), not a track record: it still passes, is marked, and counts as only
# this much when ranking, so the list is not led by base effects.
LOW_BASE_GROWTH_PCT = 100.0
RANK_GROWTH_CAP_PCT = 40.0


@dataclass(frozen=True)
class Inputs:
    symbol: str
    name: str
    sector: str | None
    fundamental: float | None
    solvency: float | None
    valuation_status: str | None
    strength: float | None
    from_high_pct: float | None  # negative when below the one-year high
    market_cap: float | None
    quarters: list[exp.Quarter]
    annuals: list[exp.Annual]


@dataclass(frozen=True)
class Check:
    key: str
    label: str
    passed: bool | None  # None: not enough data to say
    detail: str


@dataclass(frozen=True)
class Result:
    symbol: str
    name: str
    sector: str | None
    checks: list[Check]
    passes: int
    needed_growth_pct: float | None
    own_growth_pct: float | None
    gap_points: float | None
    low_base: bool
    rank_gap: float | None  # the gap with growth capped, used only for ranking
    fundamental: float | None
    strength: float | None
    from_high_pct: float | None
    valuation_status: str | None


def _ok(value: bool | None) -> bool | None:
    return value


def evaluate(i: Inputs) -> Result:
    # 1. Good business.
    if i.fundamental is None or i.solvency is None:
        q = Check("quality", "Good business", None, "Not enough statements stored")
    else:
        q = Check(
            "quality",
            "Good business",
            i.fundamental >= MIN_FUNDAMENTAL and i.solvency >= MIN_SOLVENCY,
            f"Fundamental {i.fundamental:.0f} (needs {MIN_FUNDAMENTAL:.0f}+), "
            f"solvency {i.solvency:.0f} (needs {MIN_SOLVENCY:.0f}+)",
        )

    # 2. Price assumes little.
    result = exp.assess(i.market_cap, i.quarters, i.annuals, [])
    needed = own = gap = rank_gap = None
    low_base = False
    if result.status != "ok":
        e = Check("expectations", "Price assumes little", None, "No profit to compare (loss-making or no data)")
    else:
        central = next(x for x in result.implied if x.rate == exp.DISCOUNT_RATE)
        needed = round(central.growth * 100.0, 1)
        own_raw = result.own.earnings_growth
        own = round(own_raw * 100.0, 1) if own_raw is not None else None
        if own is None or central.bound:
            e = Check("expectations", "Price assumes little", None,
                      f"Price needs {needed:.1f}% a year; no clean earnings growth to compare")
        else:
            gap = round(own - needed, 1)
            low_base = own > LOW_BASE_GROWTH_PCT
            rank_gap = round(min(own, RANK_GROWTH_CAP_PCT) - needed, 1)
            e = Check(
                "expectations",
                "Price assumes little",
                needed <= MAX_NEEDED_GROWTH_PCT and gap >= MIN_GROWTH_GAP_POINTS,
                f"Price needs {needed:.1f}% a year (max {MAX_NEEDED_GROWTH_PCT:.0f}%); "
                f"it grew {own:.1f}% a year"
                + (" from a very low starting profit" if low_base else "")
                + f" (gap {gap:+.1f}, needs {MIN_GROWTH_GAP_POINTS:.0f}+)",
            )

    # 3. Cheap against peers.
    v = Check(
        "valuation",
        "Cheap against peers",
        (i.valuation_status == "undervalued") if i.valuation_status else None,
        f"Peer valuation: {i.valuation_status.replace('_', ' ')}" if i.valuation_status
        else "No peer valuation stored",
    )

    # 4. Not yet re-rated.
    if i.strength is None or i.from_high_pct is None:
        r = Check("rerating", "Not yet re-rated", None, "Not enough price history")
    else:
        r = Check(
            "rerating",
            "Not yet re-rated",
            i.strength <= MAX_STRENGTH and i.from_high_pct <= -MIN_BELOW_HIGH_PCT,
            f"Strength {i.strength:.0f} (max {MAX_STRENGTH:.0f}), "
            f"{abs(i.from_high_pct):.1f}% below its one-year high (min {MIN_BELOW_HIGH_PCT:.0f}%)",
        )

    checks = [q, e, v, r]
    return Result(
        symbol=i.symbol,
        name=i.name,
        sector=i.sector,
        checks=checks,
        passes=sum(1 for c in checks if c.passed),
        needed_growth_pct=needed,
        own_growth_pct=own,
        gap_points=gap,
        low_base=low_base,
        rank_gap=rank_gap,
        fundamental=i.fundamental,
        strength=i.strength,
        from_high_pct=i.from_high_pct,
        valuation_status=i.valuation_status,
    )


def rank_key(r: Result) -> tuple:
    """Most checks first, then the widest gap between what the company grew
    (capped, so a recovery from a tiny profit does not lead) and what the
    price needs, then the stronger business, then the symbol (stable order)."""
    return (
        -r.passes,
        -(r.rank_gap if r.rank_gap is not None else -1e9),
        -(r.fundamental if r.fundamental is not None else 0.0),
        r.symbol,
    )
