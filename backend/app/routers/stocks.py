# Stock endpoints: list the universe + fetch price history.
#
# Concepts:
#  - APIRouter: groups related routes into one module; main.py includes it with
#    a URL prefix.
#  - Pydantic response models: declare the exact JSON shape. FastAPI validates
#    and serializes output and documents it in Swagger. Decimal DB values are
#    exposed as float here (Decimal isn't JSON-serializable).
#  - Depends(get_session): dependency injection — FastAPI supplies an
#    AsyncSession per request and auto-closes it (from app.db).
#  - SQLAlchemy select() + func: build queries; func.count() for totals.

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import NotFoundError, ValidationError
from app.models import DailyPrice, Stock
from app.repositories import financials as fin_repo
from app.repositories import prices as price_repo
from app.routers.common import resolve_stock
from app.services import freshness

router = APIRouter(prefix="/stocks", tags=["stocks"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Map a range string to a lookback of calendar days.
RANGES: dict[str, int] = {
    "1d": 1,
    "5d": 7,
    "1mo": 31,
    "3mo": 93,
    "6mo": 186,
    "1y": 366,
    "2y": 732,
}

# Default pagination + sorting.
DEFAULT_LIMIT = 50
MAX_LIMIT = 250
VALID_SORTS = ("symbol", "company", "sector", "last_price", "change_pct", "market_cap")


def normalize_symbol(symbol: str) -> str:
    """Accept 'RELIANCE' or 'reliance.ns' and normalize to 'RELIANCE.NS'."""
    s = symbol.strip().upper()
    if "." not in s:
        s += ".NS"
    return s


# --- Response models ---


class StockSummary(BaseModel):
    """One row in the stock list.

    last_price/change_pct are None when the stock has no stored price bars —
    the list never fabricates zeros for missing data.
    """

    model_config = ConfigDict(from_attributes=True)

    symbol: str
    name: str
    sector: str | None
    industry: str | None
    last_price: float | None
    change_pct: float | None
    market_cap: float | None


class StockListResponse(BaseModel):
    items: list[StockSummary]
    total: int
    page: int
    limit: int
    sectors: list[str]  # distinct sectors in the catalog (for filters)


class PriceBar(BaseModel):
    """One OHLCV bar in a price-history response."""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class PriceHistoryResponse(BaseModel):
    symbol: str
    range: str
    items: list[PriceBar]


class QuoteBlock(BaseModel):
    """Latest-quote block for the stock-detail header.

    Fields are nullable when the stock has no price history (or no snapshot
    data) — the API never fabricates values.
    """

    last_price: float | None
    change_abs: float | None
    change_pct: float | None
    open: float | None
    high: float | None
    low: float | None
    prev_close: float | None
    volume: int | None
    date: date | None  # date of the latest bar (data freshness anchor)
    # True when the latest bar is older than the price freshness TTL
    # (services/freshness.py); None when there is no bar date at all.
    stale: bool | None = None


class StockDetailResponse(BaseModel):
    """Profile + quote for the deep-linked stock page (PLANNING §9)."""

    symbol: str
    name: str
    sector: str | None
    industry: str | None
    market_cap: float | None
    quote: QuoteBlock


# --- Endpoints ---


@router.get("", response_model=StockListResponse)
async def list_stocks(
    session: SessionDep,
    sector: str | None = None,
    sort: str = Query("symbol"),
    direction: str = Query("asc"),
    page: int = Query(1, ge=1),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> StockListResponse:
    """List stocks in the catalog with price, change and market cap.

    Sorting is server-side (the catalog is a few hundred rows, loaded once
    and sorted in Python so the derived last_price/change_pct columns can be
    ordered with them). Null sort values sort last in both directions.
    """
    if sort not in VALID_SORTS:
        raise ValidationError(
            "Unsupported sort value",
            {"sort": sort, "supported": list(VALID_SORTS)},
        )
    if direction not in ("asc", "desc"):
        raise ValidationError(
            "Unsupported direction value",
            {"direction": direction, "supported": ["asc", "desc"]},
        )

    # Distinct sectors for the frontend's filter dropdowns.
    sectors = list(
        (
            await session.execute(
                select(Stock.sector).where(Stock.sector.is_not(None)).distinct().order_by(Stock.sector)
            )
        ).scalars()
    )

    # Total count (respecting sector filter).
    count_q = select(func.count(Stock.id))
    if sector:
        count_q = count_q.where(Stock.sector == sector)
    total = (await session.execute(count_q)).scalar_one()

    q = select(Stock)
    if sector:
        q = q.where(Stock.sector == sector)
    q = q.order_by(Stock.symbol)
    stocks = (await session.execute(q)).scalars().all()

    # Batch-load the derived columns for ALL matching stocks (bounded by the
    # catalog size, ~250 rows) with the existing single-query helpers.
    latest_two = await price_repo.get_two_latest(session, [st.id for st in stocks])
    financials = await fin_repo.get_financials_batch(session, stocks)

    rows: list[StockSummary] = []
    for st in stocks:
        last_two = latest_two.get(st.id, [])
        last_price: float | None = None
        change_pct: float | None = None
        if last_two:
            latest = last_two[0]
            prev = last_two[1] if len(last_two) > 1 else latest
            if prev.close:
                change_pct = round(
                    (float(latest.close) - float(prev.close)) / float(prev.close) * 100, 2
                )
            last_price = float(latest.close)
        fin = financials.get(st.id)
        market_cap = float(fin.market_cap) if fin is not None and fin.market_cap else None
        rows.append(
            StockSummary(
                symbol=st.symbol,
                name=st.name,
                sector=st.sector,
                industry=st.industry,
                last_price=last_price,
                change_pct=change_pct,
                market_cap=market_cap,
            )
        )

    reverse = direction == "desc"

    def _key(r: StockSummary):
        if sort == "company":
            return r.name.lower()
        if sort == "sector":
            return (r.sector is None, r.sector or "")
        value = getattr(r, sort)
        if value is None:
            return (1, 0.0)
        return (0, value)

    if sort in ("symbol", "company", "sector"):
        rows.sort(key=_key, reverse=reverse)
    else:
        with_value = [r for r in rows if getattr(r, sort) is not None]
        without = [r for r in rows if getattr(r, sort) is None]
        with_value.sort(key=lambda r: getattr(r, sort), reverse=reverse)
        rows = with_value + without

    start = (page - 1) * limit
    return StockListResponse(
        items=rows[start : start + limit],
        total=total,
        page=page,
        limit=limit,
        sectors=sectors,
    )


@router.get("/{symbol}", response_model=StockDetailResponse)
async def get_stock_detail(symbol: str, session: SessionDep) -> StockDetailResponse:
    """Return the profile + latest quote for one stock (deep-linkable).

    Quote fields are None when the stock has no stored price bars yet; market
    cap is None when no financial snapshot exists. Nothing is fabricated.
    """
    stock = await resolve_stock(session, symbol)

    # Latest two bars → last price + daily change (same shape as the list view).
    latest_two = (await price_repo.get_two_latest(session, [stock.id])).get(stock.id, [])

    open_ = high = low = last = prev_close = change_abs = change_pct = None
    volume = bar_date = None
    if latest_two:
        latest = latest_two[0]
        prev = latest_two[1] if len(latest_two) > 1 else None
        last = float(latest.close)
        open_ = float(latest.open)
        high = float(latest.high)
        low = float(latest.low)
        volume = latest.volume
        bar_date = latest.date
        if prev is not None and prev.close:
            prev_close = float(prev.close)
            change_abs = round(last - prev_close, 2)
            change_pct = round((last - prev_close) / prev_close * 100, 2)

    # Market cap comes from the financials snapshot (None when absent).
    fin_row = await fin_repo.get_financials_row(session, stock)
    market_cap = float(fin_row.market_cap) if fin_row and fin_row.market_cap else None

    return StockDetailResponse(
        symbol=stock.symbol,
        name=stock.name,
        sector=stock.sector,
        industry=stock.industry,
        market_cap=market_cap,
        quote=QuoteBlock(
            last_price=last,
            change_abs=change_abs,
            change_pct=change_pct,
            open=open_,
            high=high,
            low=low,
            prev_close=prev_close,
            volume=volume,
            date=bar_date,
            stale=freshness.is_stale(bar_date, freshness.PRICE_TTL),
        ),
    )


@router.get("/{symbol}/prices", response_model=PriceHistoryResponse)
async def get_price_history(
    symbol: str,
    session: SessionDep,
    range: str = Query("1y"),
    resample: str = Query("1d"),
) -> PriceHistoryResponse:
    """Return OHLCV history for a stock over a lookback window.

    range: 1d | 5d | 1mo | 3mo | 6mo | 1y | 2y.
    resample: only '1d' supported in v1 (weekly/monthly aggregation deferred).
    """
    sym = normalize_symbol(symbol)

    if resample != "1d":
        raise ValidationError(
            "Unsupported resample value",
            {"resample": resample, "supported": ["1d"]},
        )
    if range not in RANGES:
        raise ValidationError(
            "Unsupported range value",
            {"range": range, "supported": list(RANGES.keys())},
        )

    stock = await session.scalar(select(Stock).where(Stock.symbol == sym))
    if stock is None:
        raise NotFoundError(f"Stock {sym} not found", {"symbol": sym})

    start = date.today() - timedelta(days=RANGES[range])
    rows = (
        await session.execute(
            select(DailyPrice)
            .where(DailyPrice.stock_id == stock.id, DailyPrice.date >= start)
            .order_by(DailyPrice.date.asc())
        )
    ).scalars().all()

    items = [
        PriceBar(
            date=r.date,
            open=float(r.open),
            high=float(r.high),
            low=float(r.low),
            close=float(r.close),
            volume=r.volume,
        )
        for r in rows
    ]

    return PriceHistoryResponse(symbol=sym, range=range, items=items)