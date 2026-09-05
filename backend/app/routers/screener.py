# Screener endpoint — filter the universe by valuation status and score minimums.

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import ValidationError
from app.repositories import stocks as stock_repo
from app.services import analysis

router = APIRouter(prefix="/screener", tags=["screener"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

VALID_STATUSES = ("undervalued", "overvalued", "fairly_valued")
VALID_SORTS = ("symbol", "company", "sector", "profitability", "solvency", "margin_pct")
DEFAULT_LIMIT = 50
MAX_LIMIT = 250


class ScreenResult(BaseModel):
    symbol: str
    name: str
    sector: str | None
    industry: str | None
    profitability: int | None
    solvency: int | None
    valuation_status: str | None
    margin_pct: float | None


class ScreenerResponse(BaseModel):
    items: list[ScreenResult]
    total: int
    page: int
    limit: int


@router.get("", response_model=ScreenerResponse)
async def screener(
    session: SessionDep,
    status: str | None = None,
    sector: str | None = None,
    min_profitability: float | None = Query(None, ge=0, le=100),
    min_solvency: float | None = Query(None, ge=0, le=100),
    sort: str = Query("symbol"),
    direction: str = Query("asc"),
    page: int = Query(1, ge=1),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> ScreenerResponse:
    """Screen the universe by valuation status, sector and/or score minimums.

    Business logic lives in the analysis service; this router only resolves
    symbols, applies the filters, sorts, and paginates. Rows with a null sort
    value always sort last in both directions.
    """
    if status is not None and status not in VALID_STATUSES:
        raise ValidationError(
            "Unsupported status value",
            {"status": status, "supported": list(VALID_STATUSES)},
        )
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

    symbols = await stock_repo.list_all_symbols(session)
    results: list[ScreenResult] = []

    for sym in symbols:
        stock = await stock_repo.get_stock(session, sym)
        if sector and stock.sector != sector:
            continue
        a = await analysis.analyze_stock(session, stock)

        if status and a.valuation_status != status:
            continue
        if min_profitability is not None and (
            a.profitability is None or a.profitability < min_profitability
        ):
            continue
        if min_solvency is not None and (
            a.solvency is None or a.solvency < min_solvency
        ):
            continue

        results.append(
            ScreenResult(
                symbol=a.symbol,
                name=a.name,
                sector=a.sector,
                industry=a.industry,
                profitability=a.profitability,
                solvency=a.solvency,
                valuation_status=a.valuation_status,
                margin_pct=a.margin_pct,
            )
        )

    reverse = direction == "desc"

    def _sort_key(r: ScreenResult):
        if sort == "company":
            return r.name.lower()
        if sort == "sector":
            return (r.sector is None, r.sector or "")
        # Score-style columns: nulls last regardless of direction.
        value = getattr(r, sort)
        if value is None:
            return (1, 0.0) if sort != "symbol" else (1, "")
        return (0, value)

    if sort in ("symbol", "company", "sector"):
        results.sort(key=_sort_key, reverse=reverse)
    else:
        results.sort(key=_sort_key, reverse=False)
        if reverse:
            # Numeric columns: highest first, but nulls still last.
            with_value = [r for r in results if getattr(r, sort) is not None]
            without = [r for r in results if getattr(r, sort) is None]
            with_value.sort(key=lambda r: getattr(r, sort), reverse=True)
            results = with_value + without

    total = len(results)
    start = (page - 1) * limit
    page_items = results[start : start + limit]

    return ScreenerResponse(items=page_items, total=total, page=page, limit=limit)