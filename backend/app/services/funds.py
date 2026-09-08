# Fund windowed returns — pure math over stored NAV points (Plan 8.2 slice).
#
# return over a window: (latest NAV / NAV on-or-just-before window start - 1).
# "Just before" uses the first point AT OR AFTER the target date, so a
# weekend/holiday start never silently shifts the anchor forward weeks. Fewer
# than two points, or no anchor within the stored series, means the window
# does not exist yet: None, never a fabricated 0.

from datetime import date, timedelta

# Window label -> calendar-day lookback. 1m=30d, 3m=91d, 6m=182d.
FUND_WINDOWS: dict[str, int] = {"1m": 30, "3m": 91, "6m": 182}


def window_returns(
    points: list[tuple[date, float]], windows: dict[str, int] | None = None
) -> dict[str, float | None]:
    """Return {window_label: pct_return | None} over chronological NAV points.

    points: [(date, nav)] oldest-first, deduplicated by date.
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
        anchor: float | None = None
        for d, nav in points:  # chronological; first point at/after target
            if d >= target:
                if nav > 0:
                    anchor = nav
                break
        out[label] = (
            round((latest_nav / anchor - 1.0) * 100.0, 2) if anchor else None
        )
    return out
