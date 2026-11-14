# Fund returns and risk from the small rows the funds database works out
# (repositories/funds_db.return_inputs). Pure, no I/O.
#
# Windows up to six months are plain percent changes; one year and longer
# are yearly rates (CAGR), as in services/funds.window_returns. Since launch
# is a yearly rate once the fund is over a year old. Volatility is the last
# year's daily changes scaled to a year (needs 120 points); the deepest fall
# is over the last three years. Rank: by one-year return within the
# category, 1 = best, among funds that have a one-year return.

from datetime import date

YEARLY_FROM_DAYS = 365
MIN_VOL_POINTS = 120
TRADING_DAYS = 252
LABELS = ("1m", "3m", "6m", "1y", "3y", "5y", "10y")


def _pct(v: float | None) -> float | None:
    return round(v * 100.0, 4) if v is not None else None


def _rate(ratio: float, days: int) -> float:
    if days >= YEARLY_FROM_DAYS:
        return ratio ** (365.0 / days) - 1.0
    return ratio - 1.0


def compute(anchors, series, meta: dict[int, tuple[str | None, date | None]]) -> list[dict]:
    """fund_returns rows for every fund in `meta` (active funds).

    anchors: rows of (id, label, days, last_nav, anchor_nav).
    series: rows of (id, first_day, first_nav, daily_sd, year_points, drawdown).
    meta: {fund id: (category, latest NAV date)}.
    """
    rets: dict[int, dict[str, float | None]] = {}
    last_nav: dict[int, float] = {}
    for r in anchors:
        last_nav[r.id] = r.last_nav
        ok = r.anchor_nav is not None and r.anchor_nav > 0 and r.last_nav
        rets.setdefault(r.id, {})[r.label] = _rate(r.last_nav / r.anchor_nav, r.days) if ok else None

    extra = {r.id: r for r in series}
    rows: list[dict] = []
    for fund_id, (_, last_day) in meta.items():
        got = rets.get(fund_id, {})
        s = extra.get(fund_id)
        since = vol = drawdown = None
        if s is not None:
            nav = last_nav.get(fund_id)
            if s.first_nav and s.first_nav > 0 and nav and s.first_day and last_day:
                span = (last_day - s.first_day).days
                if span > 0:
                    since = _rate(nav / s.first_nav, span)
            if s.daily_sd is not None and (s.year_points or 0) >= MIN_VOL_POINTS:
                vol = s.daily_sd * TRADING_DAYS ** 0.5
            drawdown = s.drawdown
        rows.append(
            {
                "fund_id": fund_id,
                "as_of": last_day,
                **{f"ret_{k}": _pct(got.get(k)) for k in LABELS},
                "ret_since_launch": _pct(since),
                "volatility_pct": _pct(vol),
                "max_drawdown_pct": _pct(drawdown),
                "category_rank": None,
                "category_size": None,
            }
        )

    by_category: dict[str, list[dict]] = {}
    for row in rows:
        category = meta[row["fund_id"]][0]
        if category and row["ret_1y"] is not None:
            by_category.setdefault(category, []).append(row)
    for group in by_category.values():
        group.sort(key=lambda r: (-r["ret_1y"], r["fund_id"]))
        for i, row in enumerate(group):
            row["category_rank"] = i + 1
            row["category_size"] = len(group)
    return rows
