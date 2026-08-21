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
from app.repositories import prices as price_repo

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

# Default pagination.
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def normalize_symbol(symbol: str) -> str:
    """Accept 'RELIANCE' or 'reliance.ns' and normalize to 'RELIANCE.NS'."""
    s = symbol.strip().upper()
    if "." not in s:
        s += ".NS"
    return s


# --- Response models ---


class StockSummary(BaseModel):
    """One row in the stock list."""

    model_config = ConfigDict(from_attributes=True)

    symbol: str
    name: str
    sector: str | None
    last_price: float
    change_pct: float


class StockListResponse(BaseModel):
    items: list[StockSummary]
    total: int
    page: int
    limit: int


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


# --- Endpoints ---


@router.get("", response_model=StockListResponse)
async def list_stocks(
    session: SessionDep,
    sector: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> StockListResponse:
    """List stocks in the catalog, with the latest price + daily change."""

    # Total count (respecting sector filter).
    count_q = select(func.count(Stock.id))
    if sector:
        count_q = count_q.where(Stock.sector == sector)
    total = (await session.execute(count_q)).scalar_one()

    # Page of stocks.
    q = select(Stock)
    if sector:
        q = q.where(Stock.sector == sector)
    q = q.order_by(Stock.symbol).offset((page - 1) * limit).limit(limit)
    stocks = (await session.execute(q)).scalars().all()

    # Batch-load the latest two prices for ALL stocks in this page with a
    # single window-function query (avoids the old per-stock N+1 loop).
    latest_two = await price_repo.get_two_latest(
        session, [st.id for st in stocks]
    )

    items: list[StockSummary] = []
    for st in stocks:
        last_two = latest_two.get(st.id, [])

        if not last_two:
            items.append(
                StockSummary(
                    symbol=st.symbol, name=st.name, sector=st.sector,
                    last_price=0.0, change_pct=0.0,
                )
            )
            continue

        latest = last_two[0]
        prev = last_two[1] if len(last_two) > 1 else latest
        change_pct = 0.0
        if prev.close:
            change_pct = round(
                (float(latest.close) - float(prev.close)) / float(prev.close) * 100, 2
            )

        items.append(
            StockSummary(
                symbol=st.symbol,
                name=st.name,
                sector=st.sector,
                last_price=float(latest.close),
                change_pct=change_pct,
            )
        )

    return StockListResponse(items=items, total=total, page=page, limit=limit)


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