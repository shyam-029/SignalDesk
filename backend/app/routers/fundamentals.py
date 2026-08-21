# Fundamentals endpoint — returns the stored financial snapshot (key_ratios).

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import NotFoundError
from app.models import Stock
from app.repositories import financials as fin_repo
from app.routers.common import resolve_stock

router = APIRouter(prefix="/stocks", tags=["fundamentals"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class FundamentalsResponse(BaseModel):
    symbol: str
    key_ratios: dict[str, float | None]
    updated_at: str | None = None


@router.get("/{symbol}/fundamentals", response_model=FundamentalsResponse)
async def get_fundamentals(symbol: str, session: SessionDep) -> FundamentalsResponse:
    """Return the stored financial snapshot (key ratios) for a stock.

    Only stored ratios are returned (PLANNING §9 lists statements we don't
    persist — income/balance_sheet/cash_flow are deliberately omitted in v1).
    """
    stock = await resolve_stock(session, symbol)
    row = await fin_repo.get_financials_row(session, stock)
    if row is None:
        return FundamentalsResponse(symbol=stock.symbol, key_ratios={}, updated_at=None)
    return FundamentalsResponse(
        symbol=stock.symbol,
        key_ratios=fin_repo.to_key_ratios(row),
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )