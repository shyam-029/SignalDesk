# Alpha Score endpoint — composite + separate value signal, fully explainable.

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.repositories import alpha as alpha_repo
from app.routers.common import resolve_stock
from app.services import alpha as alpha_svc

router = APIRouter(prefix="/stocks", tags=["alpha"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class ValueSignalResponse(BaseModel):
    metric: str | None
    status: str | None
    margin_pct: float | None
    explanation: str | None


class AlphaResponse(BaseModel):
    symbol: str
    date: date
    composite: float | None
    fundamental: float | None
    technical: float | None
    sentiment: float | None
    components: dict[str, float]
    weights: dict[str, float]
    value_signal: ValueSignalResponse | None
    insufficient_data: bool


@router.get("/{symbol}/alpha", response_model=AlphaResponse)
async def get_alpha(symbol: str, session: SessionDep) -> AlphaResponse:
    """Alpha Score composite (quality/momentum/tone) + separate value signal."""
    stock = await resolve_stock(session, symbol)
    result = await alpha_svc.compute_alpha(session, stock)

    # Persist a snapshot for history (idempotent by symbol+date).
    await alpha_repo.upsert_snapshot(
        session,
        symbol=stock.symbol,
        snapshot_date=date.today(),
        composite=result.composite,
        fundamental=result.fundamental,
        technical=result.technical,
        sentiment=result.sentiment,
        components_json=result.components,
    )

    return AlphaResponse(
        symbol=result.symbol,
        date=date.today(),
        composite=result.composite,
        fundamental=result.fundamental,
        technical=result.technical,
        sentiment=result.sentiment,
        components=result.components,
        weights=result.weights,
        value_signal=(
            ValueSignalResponse(
                metric=result.value_signal.metric,
                status=result.value_signal.status,
                margin_pct=result.value_signal.margin_pct,
                explanation=result.value_signal.explanation,
            )
            if result.value_signal
            else None
        ),
        insufficient_data=result.insufficient_data,
    )