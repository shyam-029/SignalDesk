# Stock-page depth: valuation history, risk and the return-on-equity breakdown.
#
# Three pure calculations over data SignalDesk already stores (daily bars,
# annual income statements, annual balance sheets, benchmark bars). No clock,
# no network, no DB: the router reads rows and hands explicit inputs in.
#
# Honesty rules, enforced here:
#   - A value that cannot be computed is None with a reason. Nothing is
#     estimated, interpolated or zero-filled.
#   - A past multiple only uses a profit figure that had been PUBLISHED by
#     that date (period end + PUBLICATION_LAG_DAYS), so the history never
#     uses numbers nobody knew yet.
#   - Past market value uses today's share count (see valuation_history):
#     stored prices are split/bonus adjusted, so price x today's shares is the
#     consistent basis. Share issuance and buybacks inside the window are not
#     corrected for; the response says so.

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median

# SEBI LODR: audited annual results are due within 60 days of the year end.
PUBLICATION_LAG_DAYS = 60

# A multiple needs this many valid daily readings before a band is shown.
MIN_BAND_POINTS = 120
# The current reading is "near" its own median inside this band (percent).
NEAR_MEDIAN_PCT = 10.0
# Series are thinned to roughly weekly points for the chart payload.
SERIES_STEP = 5

# Beta needs this many paired daily returns.
MIN_BETA_PAIRS = 120
# NSE price bands cap most stocks at 20% a day; a larger one-day move is far
# more likely an unadjusted split/bonus than a real price change.
SUSPECT_MOVE_PCT = 40.0

TRADING_DAYS = 252.0


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def _round(value: float | None, places: int = 2) -> float | None:
    return round(value, places) if _finite(value) else None


# --- Valuation history -------------------------------------------------------


@dataclass(frozen=True)
class AnnualFacts:
    """One fiscal year's stored figures (rupees). None = not supplied."""

    period_end: date
    net_income: float | None = None
    revenue: float | None = None
    book_equity: float | None = None


@dataclass
class MultipleBand:
    """One multiple (P/E, P/B or P/S) over the stored price history."""

    metric: str
    status: str  # "available" | "unavailable" | "not_applicable"
    reason: str | None = None
    current: float | None = None
    median: float | None = None
    low: float | None = None
    high: float | None = None
    # Share of valid days on which the multiple was BELOW today's reading.
    percentile: float | None = None
    # Today's reading against the stock's own median, in percent.
    vs_median_pct: float | None = None
    verdict: str | None = None  # "below" | "near" | "above"
    points_used: int = 0
    series: list[tuple[date, float]] = field(default_factory=list)


def _published_fact(
    facts: list[AnnualFacts], on: date, attr: str
) -> float | None:
    """The newest fiscal year's `attr` that was public on `on` (or None).

    `facts` is ascending by period_end. A year counts as public from its
    period end plus the publication lag.
    """
    chosen: float | None = None
    for fact in facts:
        if fact.period_end + timedelta(days=PUBLICATION_LAG_DAYS) > on:
            break
        value = getattr(fact, attr)
        # A year with the figure missing does not fall back to an older year:
        # the newest published year is the one a reader would have used.
        chosen = value
    return chosen


def _band(
    metric: str,
    bars: list[tuple[date, float]],
    facts: list[AnnualFacts],
    shares: float,
    attr: str,
) -> MultipleBand:
    readings: list[tuple[date, float]] = []
    for day, close in bars:
        denominator = _published_fact(facts, day, attr)
        # A loss, zero or missing figure makes the multiple meaningless for
        # that day; the day is skipped, never filled.
        if not _finite(denominator) or denominator <= 0 or close <= 0:
            continue
        value = close * shares / denominator
        if math.isfinite(value) and value > 0:
            readings.append((day, value))

    if len(readings) < MIN_BAND_POINTS:
        return MultipleBand(
            metric=metric,
            status="unavailable",
            reason="insufficient_history" if readings else "missing_inputs",
            points_used=len(readings),
        )

    # The band is only meaningful if it reaches the present: a stock whose
    # latest year is a loss has no current reading to place inside it.
    if readings[-1][0] != bars[-1][0]:
        return MultipleBand(
            metric=metric,
            status="unavailable",
            reason="no_current_reading",
            points_used=len(readings),
        )

    values = [v for _, v in readings]
    current = values[-1]
    mid = median(values)
    below = sum(1 for v in values if v < current)
    vs_median = (current - mid) / mid * 100.0 if mid > 0 else None
    verdict = None
    if vs_median is not None:
        if vs_median <= -NEAR_MEDIAN_PCT:
            verdict = "below"
        elif vs_median >= NEAR_MEDIAN_PCT:
            verdict = "above"
        else:
            verdict = "near"

    thinned = readings[::SERIES_STEP]
    if thinned[-1][0] != readings[-1][0]:
        thinned.append(readings[-1])

    return MultipleBand(
        metric=metric,
        status="available",
        current=_round(current),
        median=_round(mid),
        low=_round(min(values)),
        high=_round(max(values)),
        percentile=_round(below / len(values) * 100.0, 1),
        vs_median_pct=_round(vs_median, 1),
        verdict=verdict,
        points_used=len(readings),
        series=[(d, round(v, 2)) for d, v in thinned],
    )


def valuation_history(
    bars: list[tuple[date, float]],
    facts: list[AnnualFacts],
    shares: float | None,
    is_financial: bool,
) -> list[MultipleBand]:
    """P/E, P/B and P/S for every stored trading day, with the stock's own band.

    Market value on a past day = that day's close x today's share count.
    Stored closes are split/bonus adjusted, so this is the consistent basis;
    the as-reported EPS of an old year is deliberately NOT used because it
    sits on that year's share count.

    bars and facts are ascending by date. shares None (no market cap and no
    usable EPS) makes every multiple unavailable.
    """
    specs = (("pe", "net_income"), ("pb", "book_equity"), ("ps", "revenue"))
    if not bars:
        return [
            MultipleBand(metric=m, status="unavailable", reason="no_price_history")
            for m, _ in specs
        ]
    if not _finite(shares) or shares <= 0:
        return [
            MultipleBand(metric=m, status="unavailable", reason="missing_share_count")
            for m, _ in specs
        ]
    out: list[MultipleBand] = []
    for metric, attr in specs:
        # Revenue is not a meaningful base for a bank or insurer.
        if metric == "ps" and is_financial:
            out.append(
                MultipleBand(
                    metric=metric,
                    status="not_applicable",
                    reason="non_applicable_financial",
                )
            )
            continue
        out.append(_band(metric, bars, facts, shares, attr))
    return out


# --- Risk --------------------------------------------------------------------


@dataclass
class Drawdown:
    """The deepest peak-to-trough fall in a close series."""

    pct: float | None = None  # negative percent
    peak_date: date | None = None
    trough_date: date | None = None
    # First day the close was back at or above the peak; None = not yet.
    recovery_date: date | None = None
    days_to_recover: int | None = None


@dataclass
class RiskResult:
    bars_used: int
    insufficient_data: bool
    volatility_pct: float | None = None
    benchmark_volatility_pct: float | None = None
    max_drawdown: Drawdown = field(default_factory=Drawdown)
    benchmark_max_drawdown_pct: float | None = None
    # How far today's close sits below the highest close in the window.
    current_drawdown_pct: float | None = None
    beta: float | None = None
    correlation: float | None = None
    beta_pairs: int = 0
    worst_day_pct: float | None = None
    worst_day_date: date | None = None
    # Set when a one-day move is too large to be a real price change.
    suspect_move_pct: float | None = None
    suspect_move_date: date | None = None
    # Percent below the running peak, thinned for the chart.
    underwater: list[tuple[date, float]] = field(default_factory=list)


def _daily_returns(bars: list[tuple[date, float]]) -> list[tuple[date, float]]:
    out: list[tuple[date, float]] = []
    for (_, prev), (day, cur) in zip(bars, bars[1:]):
        if prev <= 0:
            continue
        r = (cur - prev) / prev
        if math.isfinite(r):
            out.append((day, r))
    return out


def suspect_move(bars: list[tuple[date, float]]) -> tuple[float | None, date | None]:
    """The largest one-day move (percent, date) when it is too big to be real.

    (None, None) when no day moves by SUSPECT_MOVE_PCT or more. Used to warn
    that the stored prices probably carry an unadjusted split or bonus.
    """
    returns = _daily_returns(bars)
    if not returns:
        return None, None
    day, move = max(returns, key=lambda item: abs(item[1]))
    if abs(move) * 100.0 >= SUSPECT_MOVE_PCT:
        return _round(move * 100.0), day
    return None, None


def _volatility_pct(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    return _round(math.sqrt(variance) * math.sqrt(TRADING_DAYS) * 100.0)


def max_drawdown(bars: list[tuple[date, float]]) -> Drawdown:
    """Deepest fall from a running peak, with when (if ever) it was recovered."""
    if len(bars) < 2:
        return Drawdown()
    peak_day, peak = bars[0]
    worst = 0.0
    worst_peak_day = worst_trough_day = None
    worst_peak = None
    for day, close in bars:
        if close > peak:
            peak_day, peak = day, close
        if peak > 0:
            fall = (close - peak) / peak
            if fall < worst:
                worst = fall
                worst_peak_day, worst_trough_day, worst_peak = peak_day, day, peak
    if worst_trough_day is None:
        # The series never closed below a prior peak.
        return Drawdown(pct=0.0)
    recovery = next(
        (d for d, c in bars if d > worst_trough_day and c >= worst_peak), None
    )
    return Drawdown(
        pct=_round(worst * 100.0),
        peak_date=worst_peak_day,
        trough_date=worst_trough_day,
        recovery_date=recovery,
        days_to_recover=(recovery - worst_trough_day).days if recovery else None,
    )


def _underwater(bars: list[tuple[date, float]]) -> list[tuple[date, float]]:
    series: list[tuple[date, float]] = []
    peak = 0.0
    for day, close in bars:
        peak = max(peak, close)
        if peak > 0:
            series.append((day, round((close - peak) / peak * 100.0, 2)))
    thinned = series[::SERIES_STEP]
    if series and thinned[-1][0] != series[-1][0]:
        thinned.append(series[-1])
    return thinned


def risk(
    bars: list[tuple[date, float]],
    benchmark_bars: list[tuple[date, float]],
) -> RiskResult:
    """Volatility, drawdown and beta over the stored history (ascending bars).

    Beta and correlation pair the stock's and the benchmark's daily returns
    on the same dates only; with too few pairs they stay None.
    """
    if len(bars) < 3:
        return RiskResult(bars_used=len(bars), insufficient_data=True)

    returns = _daily_returns(bars)
    values = [r for _, r in returns]
    result = RiskResult(bars_used=len(bars), insufficient_data=False)
    result.volatility_pct = _volatility_pct(values)
    result.max_drawdown = max_drawdown(bars)
    result.underwater = _underwater(bars)
    if result.underwater:
        result.current_drawdown_pct = result.underwater[-1][1]

    if returns:
        worst_day, worst = min(returns, key=lambda item: item[1])
        result.worst_day_pct = _round(worst * 100.0)
        result.worst_day_date = worst_day
        result.suspect_move_pct, result.suspect_move_date = suspect_move(bars)

    if len(benchmark_bars) >= 3:
        bench_returns = dict(_daily_returns(benchmark_bars))
        result.benchmark_volatility_pct = _volatility_pct(list(bench_returns.values()))
        result.benchmark_max_drawdown_pct = max_drawdown(benchmark_bars).pct
        pairs = [(r, bench_returns[d]) for d, r in returns if d in bench_returns]
        result.beta_pairs = len(pairs)
        if len(pairs) >= MIN_BETA_PAIRS:
            mean_s = sum(s for s, _ in pairs) / len(pairs)
            mean_b = sum(b for _, b in pairs) / len(pairs)
            cov = sum((s - mean_s) * (b - mean_b) for s, b in pairs)
            var_b = sum((b - mean_b) ** 2 for _, b in pairs)
            var_s = sum((s - mean_s) ** 2 for s, _ in pairs)
            if var_b > 0:
                result.beta = _round(cov / var_b)
                if var_s > 0:
                    result.correlation = _round(cov / math.sqrt(var_b * var_s))
    return result


# --- Return on equity breakdown (DuPont) -------------------------------------


@dataclass(frozen=True)
class DupontInputs:
    """One fiscal year's stored figures for the breakdown (rupees)."""

    period_end: date
    net_income: float | None = None
    revenue: float | None = None
    total_assets: float | None = None
    book_equity: float | None = None


@dataclass
class DupontYear:
    period_end: date
    roe_pct: float | None = None
    net_margin_pct: float | None = None
    asset_turnover: float | None = None
    equity_multiplier: float | None = None
    missing: list[str] = field(default_factory=list)


@dataclass
class DupontResult:
    status: str  # "available" | "unavailable" | "not_applicable"
    reason: str | None = None
    years: list[DupontYear] = field(default_factory=list)
    # Which of the three levers moved return on equity most between the
    # oldest and newest complete year: "margin" | "turnover" | "leverage".
    driver: str | None = None
    roe_change_pts: float | None = None
    from_period: date | None = None
    to_period: date | None = None


def _dupont_year(row: DupontInputs) -> DupontYear:
    missing = [
        name
        for name in ("net_income", "revenue", "total_assets", "book_equity")
        if not _finite(getattr(row, name))
    ]
    year = DupontYear(period_end=row.period_end, missing=missing)
    if missing:
        return year
    # Non-positive revenue, assets or equity make the ratios meaningless
    # (negative equity flips the sign of return on equity).
    if row.revenue <= 0 or row.total_assets <= 0 or row.book_equity <= 0:
        year.missing = ["non_positive_base"]
        return year
    margin = row.net_income / row.revenue
    turnover = row.revenue / row.total_assets
    multiplier = row.total_assets / row.book_equity
    year.net_margin_pct = _round(margin * 100.0)
    year.asset_turnover = _round(turnover)
    year.equity_multiplier = _round(multiplier)
    year.roe_pct = _round(margin * turnover * multiplier * 100.0)
    return year


def dupont(rows: list[DupontInputs], is_financial: bool) -> DupontResult:
    """Return on equity = profit margin x asset turnover x equity multiplier.

    Uses year-end balances (not averages), stated in the response. Rows are
    ascending by period end. Banks and other financials are not applicable:
    revenue over assets does not describe how a lender earns its return.
    """
    if is_financial:
        return DupontResult(status="not_applicable", reason="non_applicable_financial")
    if not rows:
        return DupontResult(status="unavailable", reason="missing_balance_sheet")

    # A year with none of the four figures carries no information; a year
    # missing only some of them stays listed with what is missing.
    years = [y for y in (_dupont_year(row) for row in rows) if len(y.missing) < 4]
    if not years:
        return DupontResult(status="unavailable", reason="missing_inputs")
    complete = [y for y in years if y.roe_pct is not None]
    if not complete:
        return DupontResult(status="unavailable", reason="missing_inputs", years=years)

    result = DupontResult(status="available", years=years)
    first, last = complete[0], complete[-1]
    levers = ("net_margin_pct", "asset_turnover", "equity_multiplier")
    if first is not last and all(
        getattr(y, name) > 0 for y in (first, last) for name in levers
    ):
        # ROE is a product, so each lever's share of the change is its log
        # ratio. Only defined while profit is positive at both ends.
        shares = {
            "margin": math.log(last.net_margin_pct / first.net_margin_pct),
            "turnover": math.log(last.asset_turnover / first.asset_turnover),
            "leverage": math.log(last.equity_multiplier / first.equity_multiplier),
        }
        result.driver = max(shares, key=lambda k: abs(shares[k]))
        result.roe_change_pts = _round(last.roe_pct - first.roe_pct)
        result.from_period = first.period_end
        result.to_period = last.period_end
    return result


# --- Quarterly results trend -------------------------------------------------

# How many of the most recent quarters are returned.
MAX_QUARTERS = 12


@dataclass(frozen=True)
class QuarterFacts:
    """One stored fiscal quarter (rupees; margins as decimals)."""

    period_end: date
    revenue: float | None = None
    net_income: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None


@dataclass
class QuarterRow:
    period_end: date
    revenue: float | None = None
    net_income: float | None = None
    operating_margin_pct: float | None = None
    net_margin_pct: float | None = None
    # Change against the same quarter one year earlier. None when that
    # quarter is not stored or its figure is not a positive base.
    revenue_yoy_pct: float | None = None
    net_income_yoy_pct: float | None = None
    net_margin_yoy_pts: float | None = None


@dataclass
class QuarterlyTrend:
    insufficient_data: bool
    quarters: list[QuarterRow] = field(default_factory=list)
    # Sales growth in the latest quarter against the quarter before it,
    # both measured year on year: "faster" | "slower" | "steady" | None.
    momentum: str | None = None
    # Consecutive latest quarters with sales above the same quarter last year.
    revenue_growth_streak: int = 0


def _growth_pct(current: float | None, base: float | None) -> float | None:
    """Percent change on a positive base; None otherwise (never off a loss)."""
    if not _finite(current) or not _finite(base) or base <= 0:
        return None
    return _round((current - base) / base * 100.0, 1)


def quarterly_trend(rows: list[QuarterFacts]) -> QuarterlyTrend:
    """Each stored quarter with its change on the same quarter a year earlier.

    Rows are ascending by period end. The year-earlier quarter is matched by
    calendar month and year exactly; a gap in the stored history leaves the
    change None rather than comparing against a different quarter.
    """
    if not rows:
        return QuarterlyTrend(insufficient_data=True)

    by_key = {(r.period_end.year, r.period_end.month): r for r in rows}
    out: list[QuarterRow] = []
    for r in rows:
        prior = by_key.get((r.period_end.year - 1, r.period_end.month))
        row = QuarterRow(
            period_end=r.period_end,
            revenue=r.revenue if _finite(r.revenue) else None,
            net_income=r.net_income if _finite(r.net_income) else None,
            operating_margin_pct=_round(r.operating_margin * 100.0, 1)
            if _finite(r.operating_margin)
            else None,
            net_margin_pct=_round(r.net_margin * 100.0, 1)
            if _finite(r.net_margin)
            else None,
        )
        if prior is not None:
            row.revenue_yoy_pct = _growth_pct(r.revenue, prior.revenue)
            row.net_income_yoy_pct = _growth_pct(r.net_income, prior.net_income)
            if _finite(r.net_margin) and _finite(prior.net_margin):
                row.net_margin_yoy_pts = _round(
                    (r.net_margin - prior.net_margin) * 100.0, 1
                )
        out.append(row)

    trend = QuarterlyTrend(insufficient_data=False, quarters=out[-MAX_QUARTERS:])

    for row in reversed(out):
        if row.revenue_yoy_pct is not None and row.revenue_yoy_pct > 0:
            trend.revenue_growth_streak += 1
        else:
            break

    if len(out) >= 2:
        latest, previous = out[-1].revenue_yoy_pct, out[-2].revenue_yoy_pct
        if latest is not None and previous is not None:
            gap = latest - previous
            trend.momentum = (
                "faster" if gap >= 2.0 else "slower" if gap <= -2.0 else "steady"
            )
    return trend
