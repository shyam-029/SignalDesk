# Packed NAV history (funds database): one row per fund per calendar year,
# `days` = day of the year (1-366), `navs` = the NAV that day. Pure helpers.

from datetime import date, timedelta


def pack(points: list[tuple[date, float]]) -> dict[int, tuple[list[int], list[float]]]:
    """[(date, nav)] -> {year: (days, navs)}, sorted by date, one NAV per day
    (the last one given wins), non-positive NAVs dropped."""
    by_day: dict[date, float] = {}
    for d, nav in points:
        if nav is not None and nav > 0:
            by_day[d] = float(nav)
    out: dict[int, tuple[list[int], list[float]]] = {}
    for d in sorted(by_day):
        days, navs = out.setdefault(d.year, ([], []))
        days.append(d.timetuple().tm_yday)
        navs.append(by_day[d])
    return out


def unpack(rows: list[tuple[int, list[int], list[float]]]) -> list[tuple[date, float]]:
    """[(year, days, navs)] -> [(date, nav)] oldest first."""
    points = []
    for yr, days, navs in rows:
        start = date(yr, 1, 1)
        points.extend((start + timedelta(days=int(d) - 1), float(n)) for d, n in zip(days, navs))
    points.sort()
    return points
