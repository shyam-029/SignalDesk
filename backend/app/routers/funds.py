# Mutual-fund endpoints — the fund research surface (Plan 8 slice).
#
# GET /funds                catalog with returns; server-side sorting
# GET /funds/categories     asset groups and categories with fund counts
# GET /funds/{id}           one fund + its stored NAV series for a window
#
# Two sources (2026-11-14): when the funds database is configured
# (FUNDS_DATABASE_URL), every direct growth plan from it, paged and
# filterable; otherwise the curated list in the stocks database, unchanged.
#
# All values come from stored AMFI/mfapi rows; missing history means missing
# returns (None), never a fabricated figure.

import logging
import time
from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import NotFoundError, ValidationError
from app.funds_db import session as funds_session
from app.repositories import funds as fund_repo
from app.repositories import funds_db as fdb
from app.services.fund_nav import unpack
from app.services.funds import FUND_WINDOWS, downsample, window_returns

router = APIRouter(prefix="/funds", tags=["funds"])
logger = logging.getLogger(__name__)

SessionDep = Annotated[AsyncSession, Depends(get_session)]

WindowLabel = Literal["1m", "3m", "6m", "1y", "3y", "5y", "10y", "all"]

VALID_SORTS = (
    "category", "name", "latest_nav", "return_1m", "return_3m", "return_6m",
    "return_1y", "return_3y", "return_5y", "return_10y",
)
ASSET_GROUPS = ("equity", "hybrid", "debt", "other")

_WINDOW_DAYS = {"1m": 30, "3m": 91, "6m": 182, "1y": 365, "3y": 1095, "5y": 1826, "10y": 3652}


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
    # Funds database only (None from the curated source).
    return_5y_pct: float | None = None
    return_10y_pct: float | None = None
    return_since_launch_pct: float | None = None
    fund_house: str | None = None
    asset_group: str | None = None
    kind: str | None = None
    category_rank: int | None = None
    category_size: int | None = None
    volatility_pct: float | None = None
    max_drawdown_pct: float | None = None


class FundListResponse(BaseModel):
    items: list[FundSummary]
    total: int
    # "funds_db" (every direct growth plan) or "curated" (the old list).
    source: str = "curated"


class CategoryCount(BaseModel):
    asset_group: str | None
    category: str | None
    count: int


class CategoryListResponse(BaseModel):
    items: list[CategoryCount]
    source: str


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
    return_5y_pct: float | None = None
    return_10y_pct: float | None = None
    return_since_launch_pct: float | None = None
    fund_house: str | None = None
    asset_group: str | None = None
    kind: str | None = None
    isin: str | None = None
    launch_date: date | None = None
    category_rank: int | None = None
    category_size: int | None = None
    volatility_pct: float | None = None
    max_drawdown_pct: float | None = None
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
    "return_5y": "return_5y_pct",
    "return_10y": "return_10y_pct",
}


_READY_TTL_S = 600
_ready: tuple[float, bool] | None = None


async def _funds_db_factory():
    """The funds session factory, but only once the funds database holds live
    funds; until its first nightly fills it, the curated list keeps serving.
    The answer is cached for ten minutes."""
    global _ready
    factory = funds_session.funds_sessionmaker()
    if factory is None:
        return None
    now = time.monotonic()
    if _ready is None or now - _ready[0] > _READY_TTL_S:
        try:
            async with factory() as fsession:
                ok = await fdb.has_live_funds(fsession)
        except Exception as exc:  # noqa: BLE001 - an asleep or unreachable funds db
            logger.warning("funds database unavailable: %s", type(exc).__name__)
            ok = False
        _ready = (now, ok)
    return factory if _ready[1] else None


def reset_cache() -> None:
    global _ready
    _ready = None


def _f(v) -> float | None:
    return float(v) if v is not None else None


def _db_fields(fund, rets, house) -> dict:
    """The fields shared by list and detail, from the funds database."""
    def r(name):
        return round(float(getattr(rets, name)), 2) if rets is not None and getattr(rets, name) is not None else None

    return {
        "id": fund.id,
        "amfi_code": fund.amfi_code,
        "name": fund.name,
        "category": fund.category,
        "plan": "Direct Plan" if fund.kind != "etf" else None,
        "option": "Growth" if fund.kind != "etf" else None,
        "latest_nav": _f(fund.latest_nav),
        "nav_date": fund.nav_date,
        "return_1m_pct": r("ret_1m"),
        "return_3m_pct": r("ret_3m"),
        "return_6m_pct": r("ret_6m"),
        "return_1y_pct": r("ret_1y"),
        "return_3y_pct": r("ret_3y"),
        "return_5y_pct": r("ret_5y"),
        "return_10y_pct": r("ret_10y"),
        "return_since_launch_pct": r("ret_since_launch"),
        "fund_house": house,
        "asset_group": fund.asset_group,
        "kind": fund.kind,
        "category_rank": rets.category_rank if rets is not None else None,
        "category_size": rets.category_size if rets is not None else None,
        "volatility_pct": r("volatility_pct"),
        "max_drawdown_pct": r("max_drawdown_pct"),
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
    asset_group: str | None = Query(None),
    q: str | None = Query(None, max_length=80),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
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

    if asset_group is not None and asset_group not in ASSET_GROUPS:
        raise ValidationError(
            "Unsupported asset_group value",
            {"asset_group": asset_group, "supported": list(ASSET_GROUPS)},
        )
    factory = await _funds_db_factory()
    if factory is not None:
        async with factory() as fsession:
            rows, total = await fdb.list_funds_page(
                fsession, sort=sort, direction=direction, category=category,
                asset_group=asset_group, q=(q or "").strip() or None,
                limit=limit, offset=offset,
            )
        return FundListResponse(
            items=[FundSummary(**_db_fields(f, r, h)) for f, r, h in rows],
            total=total,
            source="funds_db",
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


@router.get("/categories", response_model=CategoryListResponse)
async def list_categories(session: SessionDep) -> CategoryListResponse:
    """Asset groups and categories with how many live funds each holds."""
    factory = await _funds_db_factory()
    if factory is not None:
        async with factory() as fsession:
            rows = await fdb.category_counts(fsession)
        return CategoryListResponse(
            items=[CategoryCount(asset_group=a, category=c, count=n) for a, c, n in rows],
            source="funds_db",
        )
    counts: dict[str | None, int] = {}
    for fund in await fund_repo.list_funds(session):
        counts[fund.category] = counts.get(fund.category, 0) + 1
    return CategoryListResponse(
        items=[CategoryCount(asset_group=None, category=c, count=n) for c, n in sorted(counts.items(), key=lambda x: str(x[0]))],
        source="curated",
    )


async def _detail_from_funds_db(factory, fund_id: int, window: str) -> FundDetailResponse:
    async with factory() as fsession:
        found = await fdb.get_fund_full(fsession, fund_id)
        if found is None:
            raise NotFoundError(f"Fund {fund_id} not found", {"fund_id": fund_id})
        fund, rets, house = found
        points = unpack(await fdb.get_history(fsession, fund.id))
    series = points
    if window != "all" and points:
        cutoff = points[-1][0] - timedelta(days=_WINDOW_DAYS[window])
        series = [p for p in points if p[0] >= cutoff]
    sampled = downsample(series)
    fields = _db_fields(fund, rets, house)
    return FundDetailResponse(
        **fields,
        isin=fund.isin,
        launch_date=fund.launch_date,
        nav_points=len(points),
        history_start=points[0][0] if points else None,
        history_end=points[-1][0] if points else None,
        items=[NavPoint(date=d, nav=n, source="amfi") for d, n in sampled],
    )


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
    factory = await _funds_db_factory()
    if factory is not None:
        return await _detail_from_funds_db(factory, fund_id, window)
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
