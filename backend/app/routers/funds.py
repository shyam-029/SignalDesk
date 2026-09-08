# Mutual-fund endpoints — the fund research surface (Plan 8 slice).
#
# GET /funds                curated catalog with returns; server-side sorting
# GET /funds/{id}           one fund + its stored NAV series for a window
#
# All values come from stored AMFI/mfapi rows; missing history means missing
# returns (None), never a fabricated figure.

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import NotFoundError, ValidationError
from app.repositories import funds as fund_repo
from app.services.funds import FUND_WINDOWS, downsample, window_returns

router = APIRouter(prefix="/funds", tags=["funds"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

WindowLabel = Literal["1m", "3m", "6m", "1y", "3y", "all"]

VALID_SORTS = (
    "category", "name", "latest_nav", "return_1m", "return_3m", "return_6m",
    "return_1y", "return_3y",
)

_WINDOW_DAYS = {"1m": 30, "3m": 91, "6m": 182, "1y": 365, "3y": 1095}


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
    # 1y/3y are annualised (CAGR %) per the fund-industry convention.
    return_1y_pct: float | None
    return_3y_pct: float | None


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
    return_1y_pct: float | None
    return_3y_pct: float | None
    nav_points: int
    history_start: date | None
    history_end: date | None
    # The selected window's series, stride-downsampled (>=120 points look
    # smooth without plotting every trading day).
    items: list[NavPoint]


_SORT_FIELD = {
    "category": "category",
    "name": "name",
    "latest_nav": "latest_nav",
    "return_1m": "return_1m_pct",
    "return_3m": "return_3m_pct",
    "return_6m": "return_6m_pct",
    "return_1y": "return_1y_pct",
    "return_3y": "return_3y_pct",
}


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
        return_1y_pct=rets.get("1y"),
        return_3y_pct=rets.get("3y"),
    )


@router.get("", response_model=FundListResponse)
async def list_funds(
    session: SessionDep,
    sort: str = Query("name"),
    direction: str = Query("asc"),
    category: str | None = Query(None),
) -> FundListResponse:
    """Curated funds with windowed returns and server-side sorting.

    Sortable: category, name, latest NAV and every return window; nulls sort
    last in both directions (a missing window is absent data, not the worst
    return).
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

    funds = await fund_repo.list_funds(session)
    items: list[FundSummary] = []
    for fund in funds:
        if category is not None and fund.category != category:
            continue
        navs = await fund_repo.get_nav_series(session, fund.id)
        rets = window_returns([(r.date, float(r.nav)) for r in navs])
        items.append(_summary(fund, rets))

    field = _SORT_FIELD[sort]
    reverse = direction == "desc"
    with_value = [r for r in items if getattr(r, field) is not None]
    without = [r for r in items if getattr(r, field) is None]
    if field in ("category", "name"):
        with_value.sort(key=lambda r: str(getattr(r, field)).lower(), reverse=reverse)
    else:
        with_value.sort(key=lambda r: float(getattr(r, field)), reverse=reverse)
    items = with_value + without
    return FundListResponse(items=items, total=len(items))


@router.get("/{fund_id}", response_model=FundDetailResponse)
async def get_fund(
    fund_id: int,
    session: SessionDep,
    window: WindowLabel = Query("all"),
) -> FundDetailResponse:
    """One fund + its stored NAV series for the selected window.

    `all` returns the full inception-to-date history (stride-downsampled to
    120 points); 1m/3m/6m/1y/3y slice to the window first. Returns cover the
    FULL stored history regardless of the chart window.
    """
    fund = await fund_repo.get_fund(session, fund_id)
    if fund is None:
        raise NotFoundError(f"Fund {fund_id} not found", {"fund_id": fund_id})
    navs = await fund_repo.get_nav_series(session, fund.id)
    rets = window_returns([(r.date, float(r.nav)) for r in navs])

    series = navs
    if window != "all" and navs:
        cutoff = navs[-1].date - timedelta(days=_WINDOW_DAYS[window])
        series = [r for r in navs if r.date >= cutoff]
    sampled = downsample([(r.date, float(r.nav)) for r in series])
    sampled_dates = {d for d, _ in sampled}
    sampled_rows = [r for r in series if r.date in sampled_dates]

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
        return_1y_pct=rets.get("1y"),
        return_3y_pct=rets.get("3y"),
        nav_points=len(navs),
        history_start=navs[0].date if navs else None,
        history_end=navs[-1].date if navs else None,
        items=[
            NavPoint(date=r.date, nav=float(r.nav), source=r.source)
            for r in sampled_rows
        ],
    )
