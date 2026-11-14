# Edge features (chosen 2026-11-14): three read-only endpoints.
#
#   GET /stocks/{symbol}/expectations -> what growth today's price assumes
#   GET /stocks/{symbol}/setups       -> past moments that looked like today,
#                                        and what came next
#   GET /track-record                 -> the Strength back-test and the
#                                        frozen monthly lists against the
#                                        average share
#
# No provider calls, no writes. Setups and the back-test are read from rows
# the weekly pass stores (jobs.build_price_setups); the lists are frozen by
# jobs.freeze_pick_lists. Missing values are null with a reason.

import time
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.repositories import edge as edge_repo
from app.repositories import financial_periods as fp_repo
from app.repositories import financials as fin_repo
from app.routers.common import resolve_stock
from app.services import expectations as exp_svc

router = APIRouter(tags=["edge"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _f(value) -> float | None:
    return float(value) if value is not None else None


def _pct(value: float | None, digits: int = 1) -> float | None:
    return round(value * 100.0, digits) if value is not None else None


# --- What the price assumes --------------------------------------------------


class ImpliedOut(BaseModel):
    discount_rate_pct: float
    growth_pct: float
    bound: str | None  # "below" | "above" | None


class OwnRecordOut(BaseModel):
    years: int | None
    from_year_end: date | None
    to_year_end: date | None
    earnings_growth_pct: float | None
    revenue_growth_pct: float | None


class ExpectationsResponse(BaseModel):
    symbol: str
    status: str  # "ok" | "not_meaningful"
    reason: str | None
    market_value: float | None
    earnings: float | None
    earnings_basis: str | None
    earnings_period_end: date | None
    pe: float | None
    years: int
    terminal_growth_pct: float
    implied: list[ImpliedOut]
    own: OwnRecordOut
    base_rate_pct: float | None
    base_rate_windows: int
    base_rate_years: int


_RATES_TTL_S = 12 * 3600
_rates_cache: tuple[float, list[float]] | None = None


async def _base_earnings_rates(session: AsyncSession) -> list[float]:
    global _rates_cache
    now = time.monotonic()
    if _rates_cache is not None and now - _rates_cache[0] < _RATES_TTL_S:
        return _rates_cache[1]
    rows = await edge_repo.get_annual_growth_rows(session)
    earnings, _ = exp_svc.growth_windows(rows)
    _rates_cache = (now, earnings)
    return earnings


def reset_cache() -> None:
    global _rates_cache
    _rates_cache = None


@router.get("/stocks/{symbol}/expectations", response_model=ExpectationsResponse)
async def get_expectations(symbol: str, session: SessionDep) -> ExpectationsResponse:
    """The yearly earnings growth today's market value needs (reverse DCF)."""
    stock = await resolve_stock(session, symbol)
    fin = await fin_repo.get_financials_row(session, stock)
    periods = await fp_repo.get_periods(session, stock.id)
    quarters = [
        exp_svc.Quarter(p.period_end, _f(p.net_income))
        for p in periods
        if p.period_type == "quarterly"
    ]
    annuals = [
        exp_svc.Annual(p.period_end, _f(p.net_income), _f(p.revenue))
        for p in periods
        if p.period_type == "annual"
    ]
    rates = await _base_earnings_rates(session)
    result = exp_svc.assess(
        _f(fin.market_cap) if fin is not None else None, quarters, annuals, rates
    )
    own = result.own
    return ExpectationsResponse(
        symbol=stock.symbol,
        status=result.status,
        reason=result.reason,
        market_value=result.market_value,
        earnings=result.earnings,
        earnings_basis=result.earnings_basis,
        earnings_period_end=result.earnings_period_end,
        pe=result.pe,
        years=exp_svc.YEARS,
        terminal_growth_pct=exp_svc.TERMINAL_GROWTH * 100.0,
        implied=[
            ImpliedOut(
                discount_rate_pct=round(i.rate * 100.0, 1),
                growth_pct=round(i.growth * 100.0, 1),
                bound=i.bound,
            )
            for i in result.implied
        ],
        own=OwnRecordOut(
            years=own.years,
            from_year_end=own.from_year_end,
            to_year_end=own.to_year_end,
            earnings_growth_pct=_pct(own.earnings_growth),
            revenue_growth_pct=_pct(own.revenue_growth),
        ),
        base_rate_pct=_pct(result.base_rate_share),
        base_rate_windows=result.base_rate_windows,
        base_rate_years=exp_svc.BASE_RATE_YEARS,
    )


# --- Similar setups ----------------------------------------------------------


class SpreadOut(BaseModel):
    n: int
    p10: float | None = None
    p25: float | None = None
    median: float | None = None
    p75: float | None = None
    p90: float | None = None
    share_up: float | None = None
    share_beat_list: float | None = None
    median_vs_list: float | None = None
    shares: int | None = None
    from_: date | None = None
    to: date | None = None
    closeness: float | None = None


class HorizonOut(BaseModel):
    horizon: str  # "3m" | "12m"
    similar: SpreadOut
    all_samples: SpreadOut


class SetupTodayOut(BaseModel):
    strength: float
    steadiness: float
    high_rank: float
    year_return_pct: float
    from_high_pct: float


class SetupsResponse(BaseModel):
    symbol: str
    status: str  # "ok" | "none"
    asof: date | None
    today: SetupTodayOut | None
    horizons: list[HorizonOut]
    samples: int | None
    shares: int | None
    sample_from: date | None
    sample_to: date | None
    neighbours: int | None


def _spread(raw: dict | None) -> SpreadOut:
    raw = dict(raw or {"n": 0})
    if "from" in raw:
        raw["from_"] = raw.pop("from")
    return SpreadOut(**raw)


@router.get("/stocks/{symbol}/setups", response_model=SetupsResponse)
async def get_setups(symbol: str, session: SessionDep) -> SetupsResponse:
    """Past moments (any share) that looked like this share today, and what
    came next over 3 and 12 months. Rebuilt weekly."""
    stock = await resolve_stock(session, symbol)
    row = await edge_repo.get_snapshot(session, edge_repo.setups_key(stock.symbol))
    base = await edge_repo.get_snapshot(session, edge_repo.SETUPS_BASELINE_KEY)
    if row is None or base is None:
        return SetupsResponse(
            symbol=stock.symbol, status="none", asof=None, today=None, horizons=[],
            samples=None, shares=None, sample_from=None, sample_to=None, neighbours=None,
        )
    payload, bp = row.payload, base.payload
    return SetupsResponse(
        symbol=stock.symbol,
        status="ok",
        asof=row.asof,
        today=SetupTodayOut(**payload["today"]),
        horizons=[
            HorizonOut(
                horizon=h,
                similar=_spread(payload["horizons"].get(h)),
                all_samples=_spread(bp["horizons"].get(h)),
            )
            for h in ("3m", "12m")
        ],
        samples=bp.get("samples"),
        shares=bp.get("shares"),
        sample_from=bp.get("from"),
        sample_to=bp.get("to"),
        neighbours=bp.get("neighbours"),
    )


# --- Track record ------------------------------------------------------------


class CurvePoint(BaseModel):
    month: date
    top: float
    list: float


class YearRow(BaseModel):
    year: str
    top: float
    list: float
    months: int


class BacktestOut(BaseModel):
    asof: date
    top_n: int
    from_: date
    to: date
    months_count: int
    months_beat: int
    top_yearly: float
    list_yearly: float
    shares: int
    curve: list[CurvePoint]
    years: list[YearRow]
    quintiles: list[float | None]


class HoldingOut(BaseModel):
    rank: int
    symbol: str
    name: str | None
    score: float | None
    entry_date: date | None
    return_pct: float | None


class FrozenListOut(BaseModel):
    list_date: date
    rating: str
    started: bool
    return_pct: float | None
    list_average_pct: float | None
    index_pct: float | None
    holdings: list[HoldingOut]


class TrackRecordResponse(BaseModel):
    backtest: BacktestOut | None
    lists: list[FrozenListOut]
    latest_close: date | None
    index_name: str


def _backtest(payload: dict | None) -> BacktestOut | None:
    if not payload or not payload.get("curve"):
        return None
    return BacktestOut(
        asof=payload["asof"],
        top_n=payload["top_n"],
        from_=payload["from"],
        to=payload["to"],
        months_count=payload["months_count"],
        months_beat=payload["months_beat"],
        top_yearly=payload["top_yearly"],
        list_yearly=payload["list_yearly"],
        shares=payload.get("shares", 0),
        curve=payload["curve"],
        years=payload["years"],
        quintiles=payload["quintiles"],
    )


def shape_lists(data: dict) -> tuple[list[FrozenListOut], date | None]:
    """Group pick rows into lists with their returns (pure; tested)."""
    groups: dict[tuple[date, str], list] = {}
    latest: date | None = None
    for r in data["picks"]:
        groups.setdefault((r.list_date, r.rating), []).append(r)
        if r.last_date is not None and (latest is None or r.last_date > latest):
            latest = r.last_date
    out: list[FrozenListOut] = []
    for (list_date, rating), rows in groups.items():
        holdings = []
        returns = []
        for r in sorted(rows, key=lambda x: x.rank):
            ret = None
            if r.entry_close and r.last_close is not None and r.entry_close > 0:
                ret = r.last_close / r.entry_close - 1.0
                returns.append(ret)
            holdings.append(
                HoldingOut(
                    rank=r.rank,
                    symbol=r.symbol,
                    name=r.name,
                    score=_f(r.score),
                    entry_date=r.entry_date,
                    return_pct=_pct(ret, 2),
                )
            )
        avg = data["averages"].get(list_date)
        started = bool(returns)
        out.append(
            FrozenListOut(
                list_date=list_date,
                rating=rating,
                started=started,
                return_pct=_pct(sum(returns) / len(returns), 2) if started else None,
                list_average_pct=_pct(avg[0], 2) if started and avg and avg[0] is not None else None,
                index_pct=_pct(data["index"].get(list_date), 2) if started else None,
                holdings=holdings,
            )
        )
    # Newest month first; Alpha's list before Strength's within a month.
    order = {"alpha": 0, "strength": 1, "underrated": 2}
    out.sort(key=lambda x: (-x.list_date.toordinal(), order.get(x.rating, 9)))
    return out, latest


@router.get("/track-record", response_model=TrackRecordResponse)
async def get_track_record(session: SessionDep) -> TrackRecordResponse:
    """How the ratings' top picks did: the decade-long Strength back-test and
    every monthly list frozen since tracking began."""
    snap = await edge_repo.get_snapshot(session, edge_repo.STRENGTH_BACKTEST_KEY)
    data = await edge_repo.get_track_record_rows(session)
    lists, latest = shape_lists(data)
    return TrackRecordResponse(
        backtest=_backtest(snap.payload if snap else None),
        lists=lists,
        latest_close=latest,
        index_name="NIFTY 50",
    )
