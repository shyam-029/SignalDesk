# ETF endpoints — the ETF domain surface (Plan 9 slice).
#
# ETFs live in the equity catalog as is_etf stocks (prices ride the standard
# pipeline) but are surfaced ONLY here: /stocks and /screener exclude them so
# the equity research surfaces stay clean. Detail pages reuse the standard
# /stocks/{symbol} research page.

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import DailyPrice, Stock
from app.repositories import prices as price_repo

router = APIRouter(prefix="/etfs", tags=["etfs"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class EtfSummary(BaseModel):
    symbol: str
    name: str
    last_price: float | None
    change_pct: float | None
    # One-year return over stored bars; None when history is shorter.
    return_1y_pct: float | None
    as_of: date | None


class EtfListResponse(BaseModel):
    items: list[EtfSummary]
    total: int


async def _one_year_return(
    session: AsyncSession, stock_id: int, today: date
) -> tuple[float | None, date | None]:
    """1y return + as-of from stored bars (None when history is shorter)."""
    cutoff = today - timedelta(days=365)
    latest = await session.scalar(
        select(DailyPrice)
        .where(DailyPrice.stock_id == stock_id)
        .order_by(DailyPrice.date.desc())
        .limit(1)
    )
    if latest is None:
        return None, None
    anchor = await session.scalar(
        select(DailyPrice)
        .where(
            DailyPrice.stock_id == stock_id,
            DailyPrice.date >= cutoff,
            DailyPrice.date < latest.date,
        )
        .order_by(DailyPrice.date.asc())
        .limit(1)
    )
    if anchor is None or not anchor.close:
        return None, latest.date
    return round((float(latest.close) / float(anchor.close) - 1.0) * 100.0, 2), latest.date


@router.get("", response_model=EtfListResponse)
async def list_etfs(session: SessionDep) -> EtfListResponse:
    """Catalogued ETFs with the latest quote and one-year return.

    Prices are None until the nightly ETF ingestion has run; nothing is
    fabricated. Rows link to the standard stock research page.
    """
    etfs = (
        await session.execute(
            select(Stock).where(Stock.is_etf.is_(True)).order_by(Stock.symbol)
        )
    ).scalars().all()

    latest_two = await price_repo.get_two_latest(session, [e.id for e in etfs])
    today = date.today()

    items: list[EtfSummary] = []
    for etf in etfs:
        last_two = latest_two.get(etf.id, [])
        last_price = change_pct = None
        as_of = None
        if last_two:
            latest = last_two[0]
            prev = last_two[1] if len(last_two) > 1 else None
            last_price = float(latest.close)
            as_of = latest.date
            if prev is not None and prev.close:
                change_pct = round(
                    (float(latest.close) - float(prev.close)) / float(prev.close) * 100, 2
                )
        ret_1y, as_of = await _one_year_return(session, etf.id, today)
        items.append(
            EtfSummary(
                symbol=etf.symbol,
                name=etf.name,
                last_price=last_price,
                change_pct=change_pct,
                return_1y_pct=ret_1y,
                as_of=as_of,
            )
        )

    return EtfListResponse(items=items, total=len(items))
