# Altman Z-Score endpoint — financial-distress diagnostic (M1-T3/T4/T6 Part D).
#
# SEPARATE from /scores by design: the Solvency Score stays intact
# (D/E 50 / interest coverage 30 / current ratio 20) and Altman is reported
# alongside as its own block, never blended into solvency, profitability or
# the Alpha composite. The score reads real stored data only: with no
# balance-sheet table in Semester 1, every response today is
# status="unavailable" with the reason recorded — never a manufactured score.

from typing import Annotated

from fastapi import APIRouter
from fastapi import Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.repositories import financials as fin_repo
from app.routers.common import resolve_stock
from app.services import altman as altman_svc

router = APIRouter(prefix="/stocks", tags=["altman"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class AltmanResponse(BaseModel):
    symbol: str
    status: str  # "available" | "unavailable"
    score: float | None
    zone: str | None  # "safe" | "grey" | "distress" | None
    formulation: str
    inputs_used: dict[str, float]
    missing_inputs: list[str]
    reason: str | None
    detail: str | None


@router.get("/{symbol}/altman", response_model=AltmanResponse)
async def get_altman(symbol: str, session: SessionDep) -> AltmanResponse:
    """Financial-distress diagnostic for one stock (Altman Z'', 1995).

    Reads the stored financial snapshot through the single honest reader
    (services/altman.from_stored_snapshot). Pure read: no provider calls, no
    writes, deterministic per stored row.
    """
    stock = await resolve_stock(session, symbol)
    fundamentals = await fin_repo.get_financials(session, stock)
    result = altman_svc.from_stored_snapshot(
        fundamentals, sector=stock.sector, industry=stock.industry
    )
    return AltmanResponse(
        symbol=stock.symbol,
        status=result.status,
        score=result.score,
        zone=result.zone,
        formulation=result.formulation,
        inputs_used=result.inputs_used,
        missing_inputs=result.missing_inputs,
        reason=result.reason,
        detail=result.detail,
    )
