# Historical research endpoints (Phase 6.5 Part E).
#
# Five read-only endpoints over data already in PostgreSQL:
#   GET /stocks/{symbol}/performance        -> windowed price performance
#   GET /stocks/{symbol}/alpha/history      -> stored Alpha Score snapshots
#   GET /stocks/{symbol}/technicals/series  -> indicator series over time
#   GET /stocks/{symbol}/peers              -> industry peers + latest quote
#   GET /stocks/{symbol}/financials/history -> per-period income statements
#
# Rules: the backend owns every calculation (the frontend only renders);
# missing values are returned as null with explicit insufficient_data flags
# rather than filled with guesses. Calculations reuse the existing services
# and repositories — no duplicated math.

import logging
import math
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import ValidationError
from app.models import FinancialPeriod, Stock
from app.repositories import alpha as alpha_repo
from app.repositories import financial_periods as fp_repo
from app.repositories import financials as fin_repo
from app.repositories import prices as price_repo
from app.repositories import stocks as stock_repo
from app.routers.common import resolve_stock
from app.services import indicators

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stocks", tags=["history"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Performance windows: label -> calendar-day lookback. 2y is the stored
# price history, so every window is computable from the DB.
PERFORMANCE_WINDOWS: dict[str, int] = {
    "1w": 7,
    "1m": 31,
    "3m": 93,
    "6mo": 186,
    "1y": 366,
    "2y": 732,
}

VALID_PERIOD_TYPES = ("annual", "quarterly")

# Derived views over stored periods: half_yearly sums two consecutive fiscal
# quarters; three_yearly sums three consecutive fiscal years. Margins are
# recomputed from the sums (never averaged blindly); per-share EPS is never
# summed across periods. See _aggregate_period_group.
VALID_PERIOD_GROUPS = ("half_yearly", "three_yearly")


def _annualized_volatility_pct(closes: list[float]) -> float | None:
    """Annualized daily-return volatility (%) for a chronological close series.

    Sample standard deviation of daily simple returns, scaled by sqrt(252)
    trading days and expressed in percent. Returns None when fewer than
    three closes (two returns) exist or a return would divide by zero or a
    non-finite value: missing volatility is reported, never approximated.
    """
    if len(closes) < 3:
        return None
    returns: list[float] = []
    for prev, cur in zip(closes, closes[1:]):
        if prev is None or cur is None or prev <= 0:
            continue
        r = (cur - prev) / prev
        if math.isfinite(r):
            returns.append(r)
    if len(returns) < 2:
        return None
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    vol = math.sqrt(variance) * math.sqrt(252.0) * 100.0
    return round(vol, 2) if math.isfinite(vol) else None


# --- Response models -------------------------------------------------------


class WindowPerformance(BaseModel):
    """Return over one lookback window; nulls when history is too short."""

    change_pct: float | None
    change_abs: float | None
    start_close: float | None
    end_close: float | None
    start_date: date | None


class PerformanceResponse(BaseModel):
    symbol: str
    as_of: date | None
    bars_used: int
    windows: dict[str, WindowPerformance]
    high_52w: float | None
    low_52w: float | None
    # Annualized daily-return volatility over the last year, in percent.
    # None when fewer than three closes exist (never a guess).
    volatility_1y_pct: float | None
    insufficient_data: bool


class AlphaHistoryItem(BaseModel):
    date: date
    composite: float | None
    fundamental: float | None
    technical: float | None
    sentiment: float | None
    components: dict[str, Any] | None


class AlphaHistoryResponse(BaseModel):
    symbol: str
    items: list[AlphaHistoryItem]
    insufficient_data: bool


class TechnicalsSeriesItem(BaseModel):
    date: date
    close: float
    sma20: float | None
    ema12: float | None
    rsi14: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None


class TechnicalsSeriesResponse(BaseModel):
    symbol: str
    items: list[TechnicalsSeriesItem]
    insufficient_data: bool


class PeerSummary(BaseModel):
    symbol: str
    name: str
    sector: str | None
    industry: str | None
    last_price: float | None
    change_pct: float | None
    trailing_pe: float | None
    # Profitability / solvency context from the same financials snapshot the
    # scores use. Null = not available for that peer (distinct from zero).
    return_on_equity: float | None
    profit_margin: float | None
    debt_to_equity: float | None


class PeersResponse(BaseModel):
    symbol: str
    classifier: str | None  # industry (or sector fallback) used to group peers
    count: int
    items: list[PeerSummary]


class FinancialPeriodItem(BaseModel):
    period_end: date
    period_type: str
    revenue: float | None
    net_income: float | None
    operating_margin: float | None
    net_margin: float | None
    eps: float | None
    source: str
    ingested_at: str
    # Grouped views only: how many stored periods were summed into this row.
    aggregated_from: int | None = None


class FinancialsHistoryResponse(BaseModel):
    symbol: str
    items: list[FinancialPeriodItem]
    insufficient_data: bool


def _fiscal_year_end(d: date) -> int:
    """The fiscal year (ending 31 March) a period end belongs to.

    Indian fiscal year: Apr 2025-Mar 2026 is "FY2026". Periods ending
    Jan-Mar belong to the fiscal year that just ended; Apr-Dec to the next.
    """
    return d.year + 1 if d.month >= 4 else d.year


def _aggregate_period_group(rows: list[FinancialPeriod], group: str) -> FinancialPeriodItem:
    """Sum consecutive stored periods into ONE derived row.

    Revenue and net income are sums over the periods that carry them (missing
    quarters contribute nothing and an all-missing metric stays None). Net
    margin is recomputed from the summed figures; operating margin is a
    revenue-weighted mean over the periods that carry both inputs. EPS is
    per-share and is deliberately not summed. Nothing is fabricated.
    """
    revenues = [float(r.revenue) for r in rows if r.revenue is not None]
    incomes = [float(r.net_income) for r in rows if r.net_income is not None]
    revenue = sum(revenues) if revenues else None
    net_income = sum(incomes) if incomes else None

    net_margin = None
    if revenue not in (None, 0.0) and net_income is not None:
        net_margin = net_income / revenue

    op_pairs = [
        (float(r.operating_margin), float(r.revenue))
        for r in rows
        if r.operating_margin is not None and r.revenue not in (None, 0)
    ]
    operating_margin = (
        sum(m * v for m, v in op_pairs) / sum(v for _, v in op_pairs)
        if op_pairs
        else None
    )

    newest = max(rows, key=lambda r: r.period_end)
    return FinancialPeriodItem(
        period_end=newest.period_end,
        period_type=group,
        revenue=revenue,
        net_income=net_income,
        operating_margin=operating_margin,
        net_margin=net_margin,
        eps=None,
        source=newest.source,
        ingested_at=newest.ingested_at.isoformat() if newest.ingested_at else "",
        aggregated_from=len(rows),
    )


# --- Endpoints -------------------------------------------------------------


@router.get("/{symbol}/performance", response_model=PerformanceResponse)
async def get_performance(symbol: str, session: SessionDep) -> PerformanceResponse:
    """Windowed price performance + 52-week range, computed from stored bars.

    Each window compares the latest close with the last close on or before
    (as_of - N days). Windows without an old-enough bar are null: with 2y of
    stored history every window is computable, but shorter histories report
    missing windows honestly instead of approximating.
    """
    stock = await resolve_stock(session, symbol)
    bars = await price_repo.get_bars(session, stock.id)

    windows: dict[str, WindowPerformance] = {}
    if bars:
        as_of = bars[-1].date
        last_close = float(bars[-1].close)
        for label, days in PERFORMANCE_WINDOWS.items():
            target = as_of - timedelta(days=days)
            start_bar = None
            for bar in bars:  # ascending; first bar <= target is the anchor
                if bar.date <= target:
                    start_bar = bar
                else:
                    break
            if start_bar is None:
                windows[label] = WindowPerformance(
                    change_pct=None, change_abs=None,
                    start_close=None, end_close=None, start_date=None,
                )
                continue
            start_close = float(start_bar.close)
            windows[label] = WindowPerformance(
                change_pct=round((last_close - start_close) / start_close * 100, 2)
                if start_close
                else None,
                change_abs=round(last_close - start_close, 2),
                start_close=start_close,
                end_close=last_close,
                start_date=start_bar.date,
            )
    else:
        as_of = None

    high_52w = low_52w = None
    recent_closes: list[float] = []
    if bars:
        cutoff = bars[-1].date - timedelta(days=366)
        recent = [b for b in bars if b.date >= cutoff]
        if recent:
            high_52w = max(float(b.high) for b in recent)
            low_52w = min(float(b.low) for b in recent)
            recent_closes = [float(b.close) for b in recent]

    return PerformanceResponse(
        symbol=stock.symbol,
        as_of=as_of,
        bars_used=len(bars),
        windows=windows,
        high_52w=high_52w,
        low_52w=low_52w,
        volatility_1y_pct=_annualized_volatility_pct(recent_closes),
        insufficient_data=len(bars) < 2,
    )


@router.get("/{symbol}/alpha/history", response_model=AlphaHistoryResponse)
async def get_alpha_history(symbol: str, session: SessionDep) -> AlphaHistoryResponse:
    """Stored Alpha Score snapshots, oldest first (empty until scores run)."""
    stock = await resolve_stock(session, symbol)
    rows = await alpha_repo.get_history(session, stock.symbol)
    return AlphaHistoryResponse(
        symbol=stock.symbol,
        items=[
            AlphaHistoryItem(
                date=r.date,
                composite=float(r.composite) if r.composite is not None else None,
                fundamental=float(r.fundamental) if r.fundamental is not None else None,
                technical=float(r.technical) if r.technical is not None else None,
                sentiment=float(r.sentiment) if r.sentiment is not None else None,
                components=r.components_json,
            )
            for r in rows
        ],
        insufficient_data=len(rows) == 0,
    )


@router.get("/{symbol}/technicals/series", response_model=TechnicalsSeriesResponse)
async def get_technicals_series(
    symbol: str,
    session: SessionDep,
    limit: int = Query(500, ge=26, le=800),
) -> TechnicalsSeriesResponse:
    """Indicator values (SMA20/EMA12/RSI14/MACD) for every stored bar.

    Reuses the same pure indicator math as /technicals and /alpha, as full
    series. Values are null before each indicator's warm-up window; that is
    a data fact, not an error.
    """
    stock = await resolve_stock(session, symbol)
    bars = await price_repo.get_bars(session, stock.id, limit=limit)
    closes = [float(b.close) for b in bars]

    sma_vals = indicators.sma_series(closes, 20)
    ema_vals = indicators.ema_series(closes, 12)
    rsi_vals = indicators.rsi_series(closes, 14)
    macd_vals = indicators.macd_series(closes)

    items = [
        TechnicalsSeriesItem(
            date=bar.date,
            close=close,
            sma20=sma_vals[i],
            ema12=ema_vals[i],
            rsi14=rsi_vals[i],
            macd=macd_vals["macd"][i],
            macd_signal=macd_vals["signal"][i],
            macd_histogram=macd_vals["histogram"][i],
        )
        for i, (bar, close) in enumerate(zip(bars, closes))
    ]
    return TechnicalsSeriesResponse(
        symbol=stock.symbol,
        items=items,
        insufficient_data=len(closes) < 26,  # SMA20 + MACD(26) warm-up
    )


@router.get("/{symbol}/peers", response_model=PeersResponse)
async def get_peers(symbol: str, session: SessionDep) -> PeersResponse:
    """Same-industry peers with their latest quote and trailing P/E.

    Peer selection reuses the existing industry-keyed repository (sector
    fallback when industry is NULL) — the same grouping relative valuation
    uses, so the response can never disagree with the valuation endpoint.
    """
    stock = await resolve_stock(session, symbol)
    classifier = stock.industry if stock.industry is not None else stock.sector
    peers = await stock_repo.get_peers(session, stock)

    latest_two = await price_repo.get_two_latest(session, [p.id for p in peers])
    financials = await fin_repo.get_financials_batch(session, peers)

    items: list[PeerSummary] = []
    for peer in peers:
        last_two = latest_two.get(peer.id, [])
        last_price = change_pct = None
        if last_two:
            latest = last_two[0]
            prev = last_two[1] if len(last_two) > 1 else None
            last_price = float(latest.close)
            if prev is not None and prev.close:
                change_pct = round(
                    (float(latest.close) - float(prev.close)) / float(prev.close) * 100, 2
                )
        fin = financials.get(peer.id)
        items.append(
            PeerSummary(
                symbol=peer.symbol,
                name=peer.name,
                sector=peer.sector,
                industry=peer.industry,
                last_price=last_price,
                change_pct=change_pct,
                trailing_pe=float(fin.trailing_pe)
                if fin is not None and fin.trailing_pe is not None
                else None,
                return_on_equity=float(fin.return_on_equity)
                if fin is not None and fin.return_on_equity is not None
                else None,
                profit_margin=float(fin.profit_margin)
                if fin is not None and fin.profit_margin is not None
                else None,
                debt_to_equity=float(fin.debt_to_equity)
                if fin is not None and fin.debt_to_equity is not None
                else None,
            )
        )

    items.sort(key=lambda p: p.symbol)
    return PeersResponse(
        symbol=stock.symbol,
        classifier=classifier,
        count=len(items),
        items=items,
    )


@router.get("/{symbol}/financials/history", response_model=FinancialsHistoryResponse)
async def get_financials_history(
    symbol: str,
    session: SessionDep,
    period_type: str | None = Query(None),
    group: str | None = Query(None),
) -> FinancialsHistoryResponse:
    """Historical income statements per period (annual by default shown all).

    Every metric is nullable exactly as ingested: providers do not supply
    all fields for all periods and nothing is fabricated. insufficient_data
    is true until the financial-history ingestion has run for the symbol.

    `group` derives larger reporting buckets from stored periods:
    "half_yearly" sums two consecutive fiscal quarters (period_type must be
    "quarterly"); "three_yearly" sums three consecutive fiscal years
    (period_type must be "annual"). Margins are recomputed from the sums,
    EPS is never summed across periods, and every grouped row carries the
    number of periods it was built from.
    """
    if period_type is not None and period_type not in VALID_PERIOD_TYPES:
        raise ValidationError(
            "Unsupported period_type value",
            {"period_type": period_type, "supported": list(VALID_PERIOD_TYPES)},
        )
    if group is not None and group not in VALID_PERIOD_GROUPS:
        raise ValidationError(
            "Unsupported group value",
            {"group": group, "supported": list(VALID_PERIOD_GROUPS)},
        )
    if group == "half_yearly" and period_type != "quarterly":
        raise ValidationError(
            "half_yearly grouping requires quarterly periods",
            {"period_type": period_type, "required": "quarterly"},
        )
    if group == "three_yearly" and period_type != "annual":
        raise ValidationError(
            "three_yearly grouping requires annual periods",
            {"period_type": period_type, "required": "annual"},
        )

    stock: Stock = await resolve_stock(session, symbol)
    rows: list[FinancialPeriod] = await fp_repo.get_periods(
        session, stock.id, period_type=period_type
    )

    if group is None:
        items = [
            FinancialPeriodItem(
                period_end=r.period_end,
                period_type=r.period_type,
                revenue=float(r.revenue) if r.revenue is not None else None,
                net_income=float(r.net_income) if r.net_income is not None else None,
                operating_margin=float(r.operating_margin)
                if r.operating_margin is not None
                else None,
                net_margin=float(r.net_margin) if r.net_margin is not None else None,
                eps=float(r.eps) if r.eps is not None else None,
                source=r.source,
                ingested_at=r.ingested_at.isoformat() if r.ingested_at else "",
            )
            for r in rows
        ]
    elif group == "half_yearly":
        # Fiscal halves of consecutive quarters: Apr-Sep (H1), Oct-Mar (H2).
        buckets: dict[tuple[int, int], list[FinancialPeriod]] = {}
        for r in rows:
            fy = _fiscal_year_end(r.period_end)
            half = 1 if 4 <= r.period_end.month <= 9 else 2
            buckets.setdefault((fy, half), []).append(r)
        items = [
            _aggregate_period_group(buckets[key], group)
            for key in sorted(buckets)
        ]
    else:  # three_yearly: three consecutive fiscal years per derived row.
        ordered = sorted(rows, key=lambda r: r.period_end)
        items = [
            _aggregate_period_group(ordered[i : i + 3], group)
            for i in range(0, len(ordered), 3)
        ]

    return FinancialsHistoryResponse(
        symbol=stock.symbol,
        items=items,
        insufficient_data=len(items) == 0,
    )
