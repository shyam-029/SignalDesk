# Precomputed price-history facts for the grounded Ask endpoint.
#
# The Ask model is not allowed to calculate (it may only restate evidence), so
# every number a question like "what was its biggest one-day move?" needs is
# computed HERE, deterministically, from the stored daily bars, and handed to
# the model as evidence. Pure functions: no I/O, no DB, no network, no LLM.
#
# Closes are the stored daily closes (as the provider returned them). Day
# changes are close-to-close percentages between consecutive stored bars; a
# gap in the stored history (holiday, missing day) is simply the next bar.

from datetime import date
from statistics import fmean

# Bars needed before any fact is offered; below this the block is omitted.
MIN_BARS = 30
# One trading year of bars (the 52-week window used elsewhere in SignalDesk).
WINDOW_BARS = 252
RECENT_CLOSES = 10
TOP_MOVES = 3

# bar = (date, close, high, low), oldest first.
Bar = tuple[date, float, float, float]


def _r(value: float, digits: int = 2) -> float:
    return round(value, digits)


def price_history_facts(bars: list[Bar]) -> dict | None:
    """Return computed daily-move facts for the last ~year, or None.

    None when fewer than MIN_BARS bars exist: SignalDesk then offers no
    history facts at all rather than a thin, misleading set.
    """
    if len(bars) < MIN_BARS:
        return None

    window = bars[-(WINDOW_BARS + 1):]  # +1 so the first change has a base
    changes: list[tuple[date, float]] = []
    for prev, cur in zip(window, window[1:]):
        if prev[1] and prev[1] > 0:
            changes.append((cur[0], (cur[1] - prev[1]) / prev[1] * 100.0))
    if not changes:
        return None

    by_pct = sorted(changes, key=lambda c: c[1])
    drops = [
        {"date": d.isoformat(), "change_pct": _r(p)} for d, p in by_pct[:TOP_MOVES] if p < 0
    ]
    gains = [
        {"date": d.isoformat(), "change_pct": _r(p)}
        for d, p in reversed(by_pct[-TOP_MOVES:]) if p > 0
    ]

    # Peak-to-trough drawdown over the window, on closes.
    peak_close, peak_date = window[0][1], window[0][0]
    worst_dd, dd_peak_date, dd_trough_date = 0.0, window[0][0], window[0][0]
    for d, close, _high, _low in window:
        if close > peak_close:
            peak_close, peak_date = close, d
        if peak_close > 0:
            dd = (close - peak_close) / peak_close * 100.0
            if dd < worst_dd:
                worst_dd, dd_peak_date, dd_trough_date = dd, peak_date, d

    year = window[1:]  # the bars whose change is counted
    high_bar = max(year, key=lambda b: b[2])
    low_bar = min(year, key=lambda b: b[3])
    last_close = window[-1][1]
    facts: dict = {
        "as_of": window[-1][0].isoformat(),
        "trading_days": len(changes),
        "biggest_gains": gains,
        "biggest_drops": drops,
        "up_days": sum(1 for _, p in changes if p > 0),
        "down_days": sum(1 for _, p in changes if p < 0),
        "avg_abs_daily_move_pct": _r(fmean(abs(p) for _, p in changes)),
        "max_drawdown_pct": _r(worst_dd),
        "max_drawdown_peak_date": dd_peak_date.isoformat(),
        "max_drawdown_trough_date": dd_trough_date.isoformat(),
        "high_52w": _r(high_bar[2]),
        "high_52w_date": high_bar[0].isoformat(),
        "low_52w": _r(low_bar[3]),
        "low_52w_date": low_bar[0].isoformat(),
    }
    if high_bar[2] > 0:
        facts["pct_from_52w_high"] = _r((last_close - high_bar[2]) / high_bar[2] * 100.0)

    recent = window[-RECENT_CLOSES:]
    recent_prev = window[-(RECENT_CLOSES + 1):-1]
    facts["recent_closes"] = [
        {
            "date": cur[0].isoformat(),
            "close": _r(cur[1]),
            "change_pct": _r((cur[1] - prev[1]) / prev[1] * 100.0)
            if prev[1] and prev[1] > 0
            else None,
        }
        for prev, cur in zip(recent_prev, recent)
    ]
    return facts
