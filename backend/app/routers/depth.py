# Stock-page depth endpoints (checklist section 6, step 1).
#
# Three read-only endpoints over data already in PostgreSQL:
#   GET /stocks/{symbol}/valuation-history -> P/E, P/B, P/S against own history
#   GET /stocks/{symbol}/risk              -> volatility, drawdown, beta
#   GET /stocks/{symbol}/quality           -> return on equity breakdown
#
# No provider calls, no writes, no new tables. The math lives in
# services/depth.py; this module only reads rows and shapes the response.
# Missing values are null with a reason, never estimated.

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Stock
from app.repositories import balance_sheets as bs_repo
from app.repositories import benchmarks as bench_repo
from app.repositories import financial_periods as fp_repo
from app.repositories import financials as fin_repo
from app.repositories import prices as price_repo
from app.routers.common import resolve_stock
from app.services import depth
from app.services.altman import is_financial_sector

router = APIRouter(prefix="/stocks", tags=["depth"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# The broad-market index beta is measured against.
RISK_BENCHMARK = "^NSEI"
RISK_BENCHMARK_NAME = "NIFTY 50"


def _f(value) -> float | None:
    return float(value) if value is not None else None


def _fiscal_year(d: date) -> int:
    """Indian fiscal year (ending 31 March) a period end belongs to."""
    return d.year + 1 if d.month >= 4 else d.year


# --- Response models -------------------------------------------------------


class SeriesPoint(BaseModel):
    date: date
    value: float


class MultipleBandOut(BaseModel):
    metric: str  # "pe" | "pb" | "ps"
    status: str  # "available" | "unavailable" | "not_applicable"
    reason: str | None
    current: float | None
    median: float | None
    low: float | None
    high: float | None
    percentile: float | None
    vs_median_pct: float | None
    verdict: str | None  # "below" | "near" | "above"
    points_used: int
    series: list[SeriesPoint]


class ValuationHistoryResponse(BaseModel):
    symbol: str
    from_date: date | None
    to_date: date | None
    # How today's share count was obtained: "market_cap" | "eps" | None.
    share_basis: str | None
    publication_lag_days: int
    # Set when a one-day price move is too large to be real (a likely
    # unadjusted split or bonus), which distorts every multiple before it.
    suspect_move_pct: float | None
    suspect_move_date: date | None
    multiples: list[MultipleBandOut]


class DrawdownOut(BaseModel):
    pct: float | None
    peak_date: date | None
    trough_date: date | None
    recovery_date: date | None
    days_to_recover: int | None


class RiskResponse(BaseModel):
    symbol: str
    from_date: date | None
    to_date: date | None
    bars_used: int
    insufficient_data: bool
    volatility_pct: float | None
    max_drawdown: DrawdownOut
    current_drawdown_pct: float | None
    worst_day_pct: float | None
    worst_day_date: date | None
    benchmark: str
    benchmark_name: str
    benchmark_volatility_pct: float | None
    benchmark_max_drawdown_pct: float | None
    beta: float | None
    correlation: float | None
    beta_pairs: int
    suspect_move_pct: float | None
    suspect_move_date: date | None
    underwater: list[SeriesPoint]


class DupontYearOut(BaseModel):
    period_end: date
    roe_pct: float | None
    net_margin_pct: float | None
    asset_turnover: float | None
    equity_multiplier: float | None
    missing: list[str]


class QualityResponse(BaseModel):
    symbol: str
    status: str  # "available" | "unavailable" | "not_applicable"
    reason: str | None
    years: list[DupontYearOut]
    driver: str | None  # "margin" | "turnover" | "leverage"
    roe_change_pts: float | None
    from_period: date | None
    to_period: date | None
    # Cash-flow statements are not stored yet, so cash-backed profit checks
    # (and the Piotroski score, which needs them) are reported as absent.
    cash_flow_available: bool


# --- Readers ---------------------------------------------------------------


async def _share_count(
    session: AsyncSession, stock: Stock, latest_close: float | None, periods
) -> tuple[float | None, str | None]:
    """Today's share count, from stored figures only.

    Preferred: stored market cap / latest stored close. Fallback: the newest
    annual net income / EPS (both positive). None when neither is usable.
    """
    fin = await fin_repo.get_financials_row(session, stock)
    market_cap = _f(fin.market_cap) if fin is not None else None
    if market_cap and market_cap > 0 and latest_close and latest_close > 0:
        return market_cap / latest_close, "market_cap"
    for period in periods:  # newest first
        net_income, eps = _f(period.net_income), _f(period.eps)
        if net_income and eps and net_income > 0 and eps > 0:
            return net_income / eps, "eps"
    return None, None


# --- Endpoints -------------------------------------------------------------


@router.get("/{symbol}/valuation-history", response_model=ValuationHistoryResponse)
async def get_valuation_history(
    symbol: str, session: SessionDep
) -> ValuationHistoryResponse:
    """Each multiple over the stored price history, against the stock's own band.

    A past day's multiple uses the newest full-year figure that had been
    published by then, and today's share count (prices are split-adjusted).
    Days where the figure is missing or negative are left out, not filled.
    """
    stock = await resolve_stock(session, symbol)
    bars = [(b.date, float(b.close)) for b in await price_repo.get_bars(session, stock.id)]
    periods = await fp_repo.get_periods(session, stock.id, period_type="annual")
    sheets = await bs_repo.get_periods(session, stock.id)

    equity_by_fy = {_fiscal_year(s.period_end): _f(s.book_equity) for s in sheets}
    facts = sorted(
        (
            depth.AnnualFacts(
                period_end=p.period_end,
                net_income=_f(p.net_income),
                revenue=_f(p.revenue),
                book_equity=equity_by_fy.get(_fiscal_year(p.period_end)),
            )
            for p in periods
        ),
        key=lambda f: f.period_end,
    )
    # A one-day move too large to be real marks an unadjusted split or bonus:
    # prices before it sit on a different share basis from today's count, so
    # only the days from that move onward are used. Nothing is rescaled.
    suspect_pct, suspect_day = depth.suspect_move(bars)
    if suspect_day is not None:
        bars = [(d, c) for d, c in bars if d >= suspect_day]
    shares, basis = await _share_count(
        session, stock, bars[-1][1] if bars else None, periods
    )
    bands = depth.valuation_history(
        bars, facts, shares, is_financial_sector(stock.sector, stock.industry)
    )
    return ValuationHistoryResponse(
        symbol=stock.symbol,
        from_date=bars[0][0] if bars else None,
        to_date=bars[-1][0] if bars else None,
        share_basis=basis,
        publication_lag_days=depth.PUBLICATION_LAG_DAYS,
        suspect_move_pct=suspect_pct,
        suspect_move_date=suspect_day,
        multiples=[
            MultipleBandOut(
                metric=b.metric,
                status=b.status,
                reason=b.reason,
                current=b.current,
                median=b.median,
                low=b.low,
                high=b.high,
                percentile=b.percentile,
                vs_median_pct=b.vs_median_pct,
                verdict=b.verdict,
                points_used=b.points_used,
                series=[SeriesPoint(date=d, value=v) for d, v in b.series],
            )
            for b in bands
        ],
    )


@router.get("/{symbol}/risk", response_model=RiskResponse)
async def get_risk(symbol: str, session: SessionDep) -> RiskResponse:
    """Volatility, deepest fall and beta against the NIFTY 50, from stored bars."""
    stock = await resolve_stock(session, symbol)
    bars = [(b.date, float(b.close)) for b in await price_repo.get_bars(session, stock.id)]
    bench = await bench_repo.get_closes(session, RISK_BENCHMARK)
    # Compare like with like: the benchmark over the stock's own date range.
    if bars:
        bench = [(d, c) for d, c in bench if bars[0][0] <= d <= bars[-1][0]]
    result = depth.risk(bars, bench)
    dd = result.max_drawdown
    return RiskResponse(
        symbol=stock.symbol,
        from_date=bars[0][0] if bars else None,
        to_date=bars[-1][0] if bars else None,
        bars_used=result.bars_used,
        insufficient_data=result.insufficient_data,
        volatility_pct=result.volatility_pct,
        max_drawdown=DrawdownOut(
            pct=dd.pct,
            peak_date=dd.peak_date,
            trough_date=dd.trough_date,
            recovery_date=dd.recovery_date,
            days_to_recover=dd.days_to_recover,
        ),
        current_drawdown_pct=result.current_drawdown_pct,
        worst_day_pct=result.worst_day_pct,
        worst_day_date=result.worst_day_date,
        benchmark=RISK_BENCHMARK,
        benchmark_name=RISK_BENCHMARK_NAME,
        benchmark_volatility_pct=result.benchmark_volatility_pct,
        benchmark_max_drawdown_pct=result.benchmark_max_drawdown_pct,
        beta=result.beta,
        correlation=result.correlation,
        beta_pairs=result.beta_pairs,
        suspect_move_pct=result.suspect_move_pct,
        suspect_move_date=result.suspect_move_date,
        underwater=[SeriesPoint(date=d, value=v) for d, v in result.underwater],
    )


@router.get("/{symbol}/quality", response_model=QualityResponse)
async def get_quality(symbol: str, session: SessionDep) -> QualityResponse:
    """Return on equity split into margin, asset turnover and leverage, per year.

    Pairs each stored annual income statement with the balance sheet of the
    same fiscal year. A year missing any input is listed with what is
    missing; it is never computed from partial figures.
    """
    stock = await resolve_stock(session, symbol)
    financial = is_financial_sector(stock.sector, stock.industry)
    rows: list[depth.DupontInputs] = []
    if not financial:
        periods = await fp_repo.get_periods(session, stock.id, period_type="annual")
        income_by_fy = {_fiscal_year(p.period_end): p for p in periods}
        for sheet in await bs_repo.get_periods(session, stock.id):  # oldest first
            income = income_by_fy.get(_fiscal_year(sheet.period_end))
            rows.append(
                depth.DupontInputs(
                    period_end=sheet.period_end,
                    net_income=_f(income.net_income) if income else None,
                    revenue=_f(income.revenue) if income else None,
                    total_assets=_f(sheet.total_assets),
                    book_equity=_f(sheet.book_equity),
                )
            )
    result = depth.dupont(rows, financial)
    return QualityResponse(
        symbol=stock.symbol,
        status=result.status,
        reason=result.reason,
        years=[
            DupontYearOut(
                period_end=y.period_end,
                roe_pct=y.roe_pct,
                net_margin_pct=y.net_margin_pct,
                asset_turnover=y.asset_turnover,
                equity_multiplier=y.equity_multiplier,
                missing=y.missing,
            )
            for y in result.years
        ],
        driver=result.driver,
        roe_change_pts=result.roe_change_pts,
        from_period=result.from_period,
        to_period=result.to_period,
        cash_flow_available=False,
    )
