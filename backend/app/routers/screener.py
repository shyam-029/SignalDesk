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
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


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
    min_profitability: float | None = Query(None, ge=0, le=100),
    min_solvency: float | None = Query(None, ge=0, le=100),
    page: int = Query(1, ge=1),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> ScreenerResponse:
    """Screen the universe by valuation status and/or score minimums.

    Business logic lives in the analysis service; this router only resolves
    symbols, applies the filters, and paginates.
    """
    if status is not None and status not in VALID_STATUSES:
        raise ValidationError(
            "Unsupported status value",
            {"status": status, "supported": list(VALID_STATUSES)},
        )

    symbols = await stock_repo.list_all_symbols(session)
    results: list[ScreenResult] = []

    for sym in symbols:
        stock = await stock_repo.get_stock(session, sym)
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

    total = len(results)
    start = (page - 1) * limit
    page_items = results[start : start + limit]

    return ScreenerResponse(items=page_items, total=total, page=page, limit=limit)