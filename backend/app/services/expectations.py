# What the price assumes (edge feature, chosen 2026-11-14). Pure math, no I/O.
#
# A reverse discounted-earnings model. Instead of guessing a growth rate and
# arriving at a "fair value", it starts from today's market value and solves
# for the yearly earnings growth that value needs:
#
#   market value = sum over years 1..10 of E0 * (1+g)^t / (1+r)^t
#                + terminal value of year-10 earnings, discounted back
#
#   terminal value = E10 * (1 + TERMINAL_GROWTH) / (r - TERMINAL_GROWTH)
#
# E0 is the latest full year of earnings (the last four quarters when they
# are stored, else the latest annual figure), r is the return an investor
# asks for (12% here, with 11% and 13% shown beside it), and after ten years
# growth settles at 6% a year, roughly India's long-run nominal growth.
# Earnings are treated as money the owners could take out; a company that
# must reinvest most of its profit to grow is flattered by that. The page
# says so.
#
# The answer is then set against two records: the company's own past growth,
# and how often any company on the list grew that fast over the stretches of
# history we hold (base rates). Nothing is estimated: a loss-making company,
# or one without a market value, gets a reason instead of a number.

from dataclasses import dataclass
from datetime import date

YEARS = 10
DISCOUNT_RATE = 0.12
DISCOUNT_RATES = (0.11, 0.12, 0.13)
TERMINAL_GROWTH = 0.06
# Search range for the implied growth rate.
G_LOW, G_HIGH = -0.5, 1.0
# Base-rate window: the growth over this many years between two annual reports.
# Most companies have four filled years stored (FY2023 to FY2026 as of
# 2026-11), so three-year stretches are the longest that cover most of them.
BASE_RATE_YEARS = 3
# A base rate over fewer company-windows than this says little.
MIN_BASE_WINDOWS = 200

REASON_NO_MARKET_VALUE = "no_market_value"
REASON_NO_EARNINGS = "no_earnings"
REASON_LOSS = "loss_making"


def present_value(earnings: float, growth: float, rate: float) -> float:
    """Today's value of `earnings` growing at `growth` for YEARS, then steady."""
    total = 0.0
    e = earnings
    for t in range(1, YEARS + 1):
        e *= 1.0 + growth
        total += e / (1.0 + rate) ** t
    terminal = e * (1.0 + TERMINAL_GROWTH) / (rate - TERMINAL_GROWTH)
    return total + terminal / (1.0 + rate) ** YEARS


@dataclass(frozen=True)
class Implied:
    """The growth a market value needs at one discount rate.

    growth is a fraction (0.15 = 15% a year). bound is "below" when even
    shrinking at G_LOW a year would be worth more than the price (the price
    assumes earnings collapse), "above" when growing at G_HIGH would be worth
    less; growth is then the bound itself.
    """

    rate: float
    growth: float
    bound: str | None


def implied_growth(market_value: float, earnings: float, rate: float) -> Implied:
    """Solve present_value(earnings, g, rate) = market_value for g (bisection).

    present_value rises with g, so bisection always converges inside the range.
    """
    if present_value(earnings, G_LOW, rate) >= market_value:
        return Implied(rate, G_LOW, "below")
    if present_value(earnings, G_HIGH, rate) <= market_value:
        return Implied(rate, G_HIGH, "above")
    lo, hi = G_LOW, G_HIGH
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if present_value(earnings, mid, rate) < market_value:
            lo = mid
        else:
            hi = mid
    return Implied(rate, round((lo + hi) / 2.0, 5), None)


@dataclass(frozen=True)
class Quarter:
    period_end: date
    net_income: float | None


@dataclass(frozen=True)
class Annual:
    period_end: date
    net_income: float | None
    revenue: float | None


def trailing_earnings(
    quarters: list[Quarter], annuals: list[Annual]
) -> tuple[float | None, str | None, date | None]:
    """The latest full year of earnings: (value, basis, period end).

    basis is "last_4_quarters" when the four newest stored quarters are all
    present and span about a year (no gap), else "latest_annual".
    """
    qs = sorted((q for q in quarters if q.net_income is not None), key=lambda q: q.period_end)
    if len(qs) >= 4:
        last4 = qs[-4:]
        span = (last4[-1].period_end - last4[0].period_end).days
        if 250 <= span <= 300:  # three quarter-steps, about 273 days
            return sum(q.net_income for q in last4), "last_4_quarters", last4[-1].period_end
    ann = sorted((a for a in annuals if a.net_income is not None), key=lambda a: a.period_end)
    if ann:
        return ann[-1].net_income, "latest_annual", ann[-1].period_end
    return None, None, None


def cagr(start: float | None, end: float | None, years: float) -> float | None:
    """Compound yearly growth from start to end; None unless both are positive."""
    if start is None or end is None or start <= 0 or end <= 0 or years <= 0:
        return None
    return (end / start) ** (1.0 / years) - 1.0


@dataclass(frozen=True)
class OwnRecord:
    """The company's own growth over the longest stored stretch (up to 5 years)."""

    years: int | None
    from_year_end: date | None
    to_year_end: date | None
    earnings_growth: float | None
    revenue_growth: float | None


def own_record(annuals: list[Annual], max_years: int = 5) -> OwnRecord:
    """Growth between the newest year and the oldest year within `max_years`
    of it that has both earnings and revenue stored (empty years skipped)."""
    ann = sorted(
        (a for a in annuals if a.net_income is not None and a.revenue is not None),
        key=lambda a: a.period_end,
    )
    if len(ann) < 2:
        return OwnRecord(None, None, None, None, None)
    end = ann[-1]
    start = next(
        a for a in ann if (end.period_end - a.period_end).days <= max_years * 365.25 + 60
    )
    years = round((end.period_end - start.period_end).days / 365.25)
    if years < 1:
        return OwnRecord(None, None, None, None, None)
    return OwnRecord(
        years=years,
        from_year_end=start.period_end,
        to_year_end=end.period_end,
        earnings_growth=cagr(start.net_income, end.net_income, years),
        revenue_growth=cagr(start.revenue, end.revenue, years),
    )


def growth_windows(
    rows: list[tuple[int, date, float | None, float | None]],
    years: int = BASE_RATE_YEARS,
) -> tuple[list[float], list[float]]:
    """Every company's earnings and revenue growth over `years`-year stretches.

    rows are (stock_id, annual period end, net income, revenue). A stretch is
    two annual reports `years` apart (within two months). Stretches that start
    from a loss are left out of the earnings list: growth from a loss has no
    rate. Returns (earnings growth rates, revenue growth rates).
    """
    by_stock: dict[int, list[tuple[date, float | None, float | None]]] = {}
    for stock_id, end, ni, rev in rows:
        by_stock.setdefault(stock_id, []).append((end, ni, rev))
    earnings: list[float] = []
    revenue: list[float] = []
    target = years * 365.25
    for items in by_stock.values():
        items.sort()
        for i, (d0, ni0, rev0) in enumerate(items):
            for d1, ni1, rev1 in items[i + 1:]:
                if abs((d1 - d0).days - target) <= 60:
                    g = cagr(ni0, ni1, years)
                    if g is not None:
                        earnings.append(g)
                    g = cagr(rev0, rev1, years)
                    if g is not None:
                        revenue.append(g)
                    break
    return earnings, revenue


def share_at_least(rates: list[float], growth: float) -> float | None:
    """Share (0 to 1) of `rates` at or above `growth`; None when too few."""
    if len(rates) < MIN_BASE_WINDOWS:
        return None
    return sum(1 for r in rates if r >= growth) / len(rates)


@dataclass(frozen=True)
class Expectations:
    status: str  # "ok" | "not_meaningful"
    reason: str | None
    market_value: float | None
    earnings: float | None
    earnings_basis: str | None
    earnings_period_end: date | None
    pe: float | None
    implied: list[Implied]
    own: OwnRecord
    base_rate_share: float | None  # share of company-windows at or above the 12% answer
    base_rate_windows: int


def assess(
    market_value: float | None,
    quarters: list[Quarter],
    annuals: list[Annual],
    base_earnings_rates: list[float],
) -> Expectations:
    own = own_record(annuals)
    earnings, basis, period_end = trailing_earnings(quarters, annuals)

    def no(reason: str) -> Expectations:
        return Expectations(
            "not_meaningful", reason, market_value, earnings, basis, period_end,
            None, [], own, None, len(base_earnings_rates),
        )

    if market_value is None or market_value <= 0:
        return no(REASON_NO_MARKET_VALUE)
    if earnings is None:
        return no(REASON_NO_EARNINGS)
    if earnings <= 0:
        return no(REASON_LOSS)
    implied = [implied_growth(market_value, earnings, r) for r in DISCOUNT_RATES]
    central = next(i for i in implied if i.rate == DISCOUNT_RATE)
    return Expectations(
        status="ok",
        reason=None,
        market_value=market_value,
        earnings=earnings,
        earnings_basis=basis,
        earnings_period_end=period_end,
        pe=round(market_value / earnings, 2),
        implied=implied,
        own=own,
        base_rate_share=share_at_least(base_earnings_rates, central.growth),
        base_rate_windows=len(base_earnings_rates),
    )
