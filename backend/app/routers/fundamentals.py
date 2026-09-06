# Fundamentals endpoint — returns the stored financial snapshot (key_ratios)
# and the stored company background profile.

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import NotFoundError
from app.models import Stock
from app.repositories import company_profiles as profile_repo
from app.repositories import financials as fin_repo
from app.routers.common import resolve_stock

router = APIRouter(prefix="/stocks", tags=["fundamentals"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class FundamentalsResponse(BaseModel):
    symbol: str
    key_ratios: dict[str, float | None]
    updated_at: str | None = None


class CompanyProfileResponse(BaseModel):
    symbol: str
    business_summary: str | None
    ceo: str | None
    employees: int | None
    website: str | None
    source: str | None = None
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


@router.get("/{symbol}/profile", response_model=CompanyProfileResponse)
async def get_company_profile(symbol: str, session: SessionDep) -> CompanyProfileResponse:
    """Provider-sourced company background (what the business does, who runs it).

    business_summary is the provider's verbatim description text — never
    generated. None fields mean the provider did not supply them.
    """
    stock = await resolve_stock(session, symbol)
    row = await profile_repo.get_profile(session, stock.id)
    if row is None:
        return CompanyProfileResponse(
            symbol=stock.symbol,
            business_summary=None,
            ceo=None,
            employees=None,
            website=None,
            source=None,
            updated_at=None,
        )
    return CompanyProfileResponse(
        symbol=stock.symbol,
        business_summary=row.business_summary,
        ceo=row.ceo,
        employees=row.employees,
        website=row.website,
        source=row.source,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )