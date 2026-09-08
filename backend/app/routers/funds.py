# Mutual-fund endpoints — the fund research surface (Plan 8 slice).
#
# GET /funds        curated catalog with latest NAV + 1m/3m/6m returns
# GET /funds/{id}   one fund + its stored NAV series (oldest-first)
#
# All values come from stored AMFI/mfapi rows; missing history means missing
# returns (None), never a fabricated figure.

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import NotFoundError
from app.repositories import funds as fund_repo
from app.services.funds import window_returns

router = APIRouter(prefix="/funds", tags=["funds"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

WindowLabel = Literal["1m", "3m", "6m"]


class FundSummary(BaseModel):
    id: int
    amfi_code: str
    name: str
    category: str | None
    plan: str | None
    option: str | None
    latest_nav: float | None
    nav_date: date | None
    return_1m_pct: float | None
    return_3m_pct: float | None
    return_6m_pct: float | None


class FundListResponse(BaseModel):
    items: list[FundSummary]
    total: int


class NavPoint(BaseModel):
    date: date
    nav: float
    source: str


class FundDetailResponse(BaseModel):
    id: int
    amfi_code: str
    name: str
    category: str | None
    plan: str | None
    option: str | None
    latest_nav: float | None
    nav_date: date | None
    return_1m_pct: float | None
    return_3m_pct: float | None
    return_6m_pct: float | None
    nav_points: int
    history_start: date | None
    history_end: date | None
    items: list[NavPoint]


def _summary(fund, rets: dict[str, float | None]) -> FundSummary:
    return FundSummary(
        id=fund.id,
        amfi_code=fund.amfi_code,
        name=fund.name,
        category=fund.category,
        plan=fund.plan,
        option=fund.option,
        latest_nav=float(fund.latest_nav) if fund.latest_nav is not None else None,
        nav_date=fund.nav_date,
        return_1m_pct=rets.get("1m"),
        return_3m_pct=rets.get("3m"),
        return_6m_pct=rets.get("6m"),
    )


@router.get("", response_model=FundListResponse)
async def list_funds(session: SessionDep) -> FundListResponse:
    """Curated funds with windowed returns from stored NAV history."""
    funds = await fund_repo.list_funds(session)
    items: list[FundSummary] = []
    for fund in funds:
        navs = await fund_repo.get_nav_series(session, fund.id)
        rets = window_returns([(r.date, float(r.nav)) for r in navs])
        items.append(_summary(fund, rets))
    return FundListResponse(items=items, total=len(items))


@router.get("/{fund_id}", response_model=FundDetailResponse)
async def get_fund(fund_id: int, session: SessionDep) -> FundDetailResponse:
    """One fund with its stored NAV series (most recent 250 points)."""
    fund = await fund_repo.get_fund(session, fund_id)
    if fund is None:
        raise NotFoundError(f"Fund {fund_id} not found", {"fund_id": fund_id})
    navs = await fund_repo.get_nav_series(session, fund.id)
    # Windowed returns use full history; the payload series is bounded.
    rets = window_returns([(r.date, float(r.nav)) for r in navs])
    series = navs[-250:]
    return FundDetailResponse(
        id=fund.id,
        amfi_code=fund.amfi_code,
        name=fund.name,
        category=fund.category,
        plan=fund.plan,
        option=fund.option,
        latest_nav=float(fund.latest_nav) if fund.latest_nav is not None else None,
        nav_date=fund.nav_date,
        return_1m_pct=rets.get("1m"),
        return_3m_pct=rets.get("3m"),
        return_6m_pct=rets.get("6m"),
        nav_points=len(navs),
        history_start=navs[0].date if navs else None,
        history_end=navs[-1].date if navs else None,
        items=[
            NavPoint(date=r.date, nav=float(r.nav), source=r.source) for r in series
        ],
    )
