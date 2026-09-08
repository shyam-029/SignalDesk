# Fund windowed returns — pure math over stored NAV points (Plan 8.2 slice).
#
# return over a window: (latest NAV / NAV on-or-just-before window start - 1).
# "Just before" uses the first point AT OR AFTER the target date, so a
# weekend/holiday start never silently shifts the anchor forward weeks. Fewer
# than two points, or no anchor within the stored series, means the window
# does not exist yet: None, never a fabricated 0.
#
# 1y/3y are expressed as CAGR (annualised), the convention for horizons over
# one year: (end/start)^(1/years) - 1.

from datetime import date, timedelta

# Window label -> calendar-day lookback. 1m/3m/6m absolute; 1y/3y CAGR.
FUND_WINDOWS: dict[str, int] = {"1m": 30, "3m": 91, "6m": 182, "1y": 365, "3y": 1095}
CAGR_WINDOWS = ("1y", "3y")


def _anchor_nav(points: list[tuple[date, float]], target: date, max_gap_days: int = 21) -> float | None:
    """First NAV at/after the target date, within a tolerance.

    A point more than `max_gap_days` after the target means the stored
    history does not actually reach the window start (e.g. a 1y window over
    8 months of data) - annualising that anchor would understate the return.
    None means the window is not covered: absent, never approximated.
    """
    for d, nav in points:
        if d >= target:
            if nav > 0 and (d - target).days <= max_gap_days:
                return nav
            return None
    return None


def window_returns(
    points: list[tuple[date, float]], windows: dict[str, int] | None = None
) -> dict[str, float | None]:
    """Return {window_label: pct_return | None} over chronological NAV points.

    points: [(date, nav)] oldest-first, deduplicated by date. Windows past
    one year are annualised (CAGR %); shorter windows are absolute %.
    """
    windows = windows or FUND_WINDOWS
    if len(points) < 2:
        return {label: None for label in windows}
    latest_date, latest_nav = points[-1]
    if latest_nav <= 0:
        return {label: None for label in windows}

    out: dict[str, float | None] = {}
    for label, days in windows.items():
        target = latest_date - timedelta(days=days)
        anchor = _anchor_nav(points, target)
        if not anchor:
            out[label] = None
            continue
        if label in CAGR_WINDOWS:
            years = days / 365.0
            out[label] = round(((latest_nav / anchor) ** (1.0 / years) - 1.0) * 100.0, 2)
        else:
            out[label] = round((latest_nav / anchor - 1.0) * 100.0, 2)
    return out


def downsample(
    points: list[tuple[date, float]], max_points: int = 120
) -> list[tuple[date, float]]:
    """Stride-sample a chronological NAV series to at most `max_points`.

    Long windows do not need every trading day to look smooth on screen: an
    even stride keeps the shape while shrinking the payload. Always keeps
    the first and last points.
    """
    if len(points) <= max_points:
        return points
    stride = (len(points) - 1) / (max_points - 1)
    out: list[tuple[date, float]] = []
    for i in range(max_points):
        idx = round(i * stride)
        if not out or out[-1][0] != points[idx][0]:
            out.append(points[idx])
    return out
