# Similar setups and the Strength back-test (edge features, 2026-11-14).
# Pure math, no I/O.
#
# Both work from about ten years of daily closes for the list's shares,
# fetched once a week and held in memory only (the database keeps two years;
# ten years of bars would not fit in the storage allowance).
#
# 1. Monthly samples. On the last trading day of every month, each share
#    gets the same ratings the nightly pass gives (services/strength:
#    Strength and Steadiness, ranked across the shares that traded that day)
#    plus where its distance from the one-year high ranks. Each sample also
#    records what came next: the return over the following 3 and 12 months
#    (63 and 252 trading days), counted from the day AFTER the sample, since
#    the ratings are only known once that day has closed.
#
# 2. Similar setups. For each share today, the K samples (any share, any
#    month) whose three ranks are closest to its own, and the spread of what
#    happened next. The share's own samples from the past year are left out:
#    they share most of today's price history.
#
# 3. Strength back-test. Every month, the 20 strongest shares, held from the
#    day after the month's last trading day to the day after the next one,
#    against the average share on the list over the same days.
#
# Limits, stated on the site: the list is today's 1,000 largest companies,
# so shares that shrank or delisted over the decade are missing (survivor
# bias, which flatters every figure, the average share's too); no trading
# costs or taxes; and the past is a description, not a forecast.

from dataclasses import dataclass, field
from datetime import date

import numpy as np

from app.services.depth import SUSPECT_MOVE_PCT
from app.services.strength import (
    HISTORY_BARS,
    SKIP_BARS,
    Inputs,
    PriceFacts,
    inputs_for,
    percentile_ranks,
    rate_list,
)

WINDOW = HISTORY_BARS - 1  # 252 daily changes inside the one-year window
HORIZONS = {"3m": 63, "12m": 252}
NEIGHBOURS = 200
OWN_EXCLUSION_DAYS = 365
TOP_N = 20
QUINTILES = 5
SUSPECT = SUSPECT_MOVE_PCT / 100.0


@dataclass
class Sample:
    symbol: str
    day: date
    strength: float
    steadiness: float
    high_rank: float
    year_return_pct: float
    from_high_pct: float
    forward: dict[str, float | None] = field(default_factory=dict)
    next_month: float | None = None


def month_ends(all_dates: set[date]) -> list[date]:
    """The last trading day of each month present (the newest month too)."""
    last: dict[tuple[int, int], date] = {}
    for d in all_dates:
        key = (d.year, d.month)
        if key not in last or d > last[key]:
            last[key] = d
    return sorted(last.values())


class _Prepared:
    """One share's closes with the rolling one-year figures worked out."""

    def __init__(self, dates: list[date], closes: np.ndarray):
        self.dates = dates
        self.c = closes.astype(float)
        self.index = {d: i for i, d in enumerate(dates)}
        n = len(self.c)
        r = np.full(n, np.nan)
        if n > 1:
            with np.errstate(divide="ignore", invalid="ignore"):
                r[1:] = self.c[1:] / self.c[:-1] - 1.0
        self.r = r
        self.abs_r = np.abs(r)

    def facts(self, i: int) -> PriceFacts | None:
        if i < WINDOW:
            return None
        c = self.c
        win_c = c[i - WINDOW + 1 : i + 1]
        win_r = self.r[i - WINDOW + 1 : i + 1]
        win_r = win_r[~np.isnan(win_r)]
        return PriceFacts(
            bars=HISTORY_BARS,
            last_date=self.dates[i],
            last_close=float(c[i]),
            close_1m=float(c[i - SKIP_BARS]),
            close_12m=float(c[i - WINDOW]),
            high_1y=float(win_c.max()),
            max_move=float(np.abs(win_r).max()) if win_r.size else None,
            daily_sd=float(win_r.std(ddof=1)) if win_r.size > 1 else None,
        )

    def ret(self, start: int, end: int) -> float | None:
        """Return from close `start` to close `end`; None past the data or
        across a one-day move too big to be real (an unadjusted split)."""
        if start < 0 or end >= len(self.c) or end <= start:
            return None
        moves = self.abs_r[start + 1 : end + 1]
        moves = moves[~np.isnan(moves)]
        if moves.size and moves.max() >= SUSPECT:
            return None
        if self.c[start] <= 0:
            return None
        return float(self.c[end] / self.c[start] - 1.0)


def build_samples(
    series: dict[str, tuple[list[date], np.ndarray]],
) -> tuple[list[date], dict[date, list[Sample]]]:
    """Monthly samples for every share, rated the way the nightly pass rates.

    series maps symbol -> (ascending dates, closes). Returns the sample days
    and, per day, the rated samples (a day with too few shares has none).
    """
    prepared = {s: _Prepared(d, c) for s, (d, c) in series.items() if len(d) > 0}
    all_dates: set[date] = set()
    for p in prepared.values():
        all_dates.update(p.dates)
    days = month_ends(all_dates)
    out: dict[date, list[Sample]] = {}
    for k, day in enumerate(days):
        nxt = days[k + 1] if k + 1 < len(days) else None
        inputs: dict[str, Inputs] = {}
        where: dict[str, int] = {}
        for sym, p in prepared.items():
            i = p.index.get(day)
            if i is None:
                continue
            facts = p.facts(i)
            if facts is None:
                continue
            got, _ = inputs_for(facts, None)
            if got is not None:
                inputs[sym] = got
                where[sym] = i
        ratings = rate_list(inputs)
        if not ratings:
            continue
        high_rank = percentile_ranks({s: i.from_high_pct for s, i in inputs.items()})
        rows: list[Sample] = []
        for sym, rating in ratings.items():
            if rating.steadiness is None:
                continue
            p = prepared[sym]
            i = where[sym]
            forward = {h: p.ret(i + 1, i + 1 + n) for h, n in HORIZONS.items()}
            next_month = None
            if nxt is not None and nxt in p.index:
                j = p.index[nxt]
                next_month = p.ret(i + 1, j + 1)
            rows.append(
                Sample(
                    symbol=sym,
                    day=day,
                    strength=rating.strength,
                    steadiness=rating.steadiness,
                    high_rank=round(high_rank[sym], 1),
                    year_return_pct=rating.year_return_pct,
                    from_high_pct=rating.from_high_pct,
                    forward=forward,
                    next_month=next_month,
                )
            )
        out[day] = rows
    return days, out


def _pct(values: np.ndarray, q: float) -> float:
    return round(float(np.percentile(values, q)) * 100.0, 1)


def summarize(returns: np.ndarray, excess: np.ndarray) -> dict:
    """The spread of what came next, in percent."""
    if returns.size == 0:
        return {"n": 0}
    return {
        "n": int(returns.size),
        "p10": _pct(returns, 10),
        "p25": _pct(returns, 25),
        "median": _pct(returns, 50),
        "p75": _pct(returns, 75),
        "p90": _pct(returns, 90),
        "share_up": round(float((returns > 0).mean()) * 100.0, 1),
        "share_beat_list": round(float((excess > 0).mean()) * 100.0, 1),
        "median_vs_list": _pct(excess, 50),
    }


@dataclass
class SampleTable:
    """All samples as arrays, with each horizon's return against the list's
    median share over the same days."""

    symbols: np.ndarray
    days: np.ndarray  # numpy datetime64[D]
    features: np.ndarray  # n x 3, each 0..1
    forward: dict[str, np.ndarray]
    excess: dict[str, np.ndarray]


def sample_table(by_day: dict[date, list[Sample]]) -> SampleTable:
    rows = [s for day in sorted(by_day) for s in by_day[day]]
    n = len(rows)
    forward = {h: np.full(n, np.nan) for h in HORIZONS}
    excess = {h: np.full(n, np.nan) for h in HORIZONS}
    pos = 0
    for day in sorted(by_day):
        group = by_day[day]
        for h in HORIZONS:
            vals = np.array(
                [s.forward[h] if s.forward.get(h) is not None else np.nan for s in group]
            )
            ok = ~np.isnan(vals)
            if ok.any():
                med = float(np.median(vals[ok]))
                forward[h][pos : pos + len(group)] = vals
                excess[h][pos : pos + len(group)] = vals - med
        pos += len(group)
    return SampleTable(
        symbols=np.array([s.symbol for s in rows]),
        days=np.array([s.day for s in rows], dtype="datetime64[D]"),
        features=np.array(
            [[s.strength / 100.0, s.steadiness / 100.0, s.high_rank / 100.0] for s in rows]
        ).reshape(n, 3),
        forward=forward,
        excess=excess,
    )


def baseline(table: SampleTable) -> dict:
    """What came next for every sample: the yardstick for a setup."""
    out = {}
    for h in HORIZONS:
        ok = ~np.isnan(table.forward[h])
        out[h] = summarize(table.forward[h][ok], table.excess[h][ok])
    return out


def similar(
    table: SampleTable,
    symbol: str,
    today: date,
    point: tuple[float, float, float],
    k: int = NEIGHBOURS,
) -> dict:
    """The k closest past samples to `point` and what came next, per horizon."""
    x = np.array(point) / 100.0
    dist = ((table.features - x) ** 2).sum(axis=1)
    cutoff = np.datetime64(today) - np.timedelta64(OWN_EXCLUSION_DAYS, "D")
    own_recent = (table.symbols == symbol) & (table.days >= cutoff)
    out: dict = {}
    for h in HORIZONS:
        ok = ~np.isnan(table.forward[h]) & ~own_recent
        idx = np.flatnonzero(ok)
        if idx.size == 0:
            out[h] = {"n": 0}
            continue
        take = min(k, idx.size)
        near = idx[np.argpartition(dist[idx], take - 1)[:take]]
        summary = summarize(table.forward[h][near], table.excess[h][near])
        summary["shares"] = int(np.unique(table.symbols[near]).size)
        summary["from"] = str(table.days[near].min())
        summary["to"] = str(table.days[near].max())
        summary["closeness"] = round(float(np.sqrt(dist[near].max())) * 100.0, 1)
        out[h] = summary
    return out


def strength_backtest(days: list[date], by_day: dict[date, list[Sample]], top_n: int = TOP_N) -> dict:
    """Each month's top `top_n` by Strength against the average share.

    A month counts only when every chosen share and at least 100 others have
    a next-month return. Quintile figures are the average yearly return of
    each fifth of the list by Strength (fifth 5 = strongest).
    """
    months = []
    quintile_logs = [[] for _ in range(QUINTILES)]
    for day in days:
        group = [s for s in by_day.get(day, []) if s.next_month is not None]
        if len(group) < 100:
            continue
        group.sort(key=lambda s: (s.strength, s.symbol))
        top = group[-top_n:]
        top_ret = float(np.mean([s.next_month for s in top]))
        list_ret = float(np.mean([s.next_month for s in group]))
        months.append(
            {
                "month": day.isoformat(),
                "top": round(top_ret * 100.0, 2),
                "list": round(list_ret * 100.0, 2),
                "picks": [s.symbol for s in reversed(top)],
            }
        )
        size = len(group) / QUINTILES
        for q in range(QUINTILES):
            part = group[int(q * size) : int((q + 1) * size)]
            quintile_logs[q].append(float(np.log1p(np.mean([s.next_month for s in part]))))
    if not months:
        return {"months": []}
    top_curve = np.cumprod([1 + m["top"] / 100.0 for m in months])
    list_curve = np.cumprod([1 + m["list"] / 100.0 for m in months])
    years = len(months) / 12.0

    def yearly(curve_end: float) -> float:
        return round((curve_end ** (1.0 / years) - 1.0) * 100.0, 1)

    by_year: dict[str, list[dict]] = {}
    for m in months:
        by_year.setdefault(m["month"][:4], []).append(m)
    return {
        "top_n": top_n,
        "from": months[0]["month"],
        "to": months[-1]["month"],
        "months_count": len(months),
        "months_beat": sum(1 for m in months if m["top"] > m["list"]),
        "top_yearly": yearly(float(top_curve[-1])),
        "list_yearly": yearly(float(list_curve[-1])),
        "curve": [
            {"month": m["month"], "top": round(float(t), 4), "list": round(float(l), 4)}
            for m, t, l in zip(months, top_curve, list_curve)
        ],
        "years": [
            {
                "year": y,
                "top": round((float(np.prod([1 + m["top"] / 100 for m in ms])) - 1) * 100, 1),
                "list": round((float(np.prod([1 + m["list"] / 100 for m in ms])) - 1) * 100, 1),
                "months": len(ms),
            }
            for y, ms in sorted(by_year.items())
        ],
        "quintiles": [
            round((float(np.exp(np.mean(q) * 12)) - 1) * 100.0, 1) if q else None
            for q in quintile_logs
        ],
        "latest_picks": months[-1]["picks"],
    }
