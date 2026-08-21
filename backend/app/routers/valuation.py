# Valuation endpoints — relative (multiples) valuation + rule-based explanation.

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import ValidationError
from app.routers.common import resolve_stock
from app.services import analysis, explanation, valuation as val_svc

router = APIRouter(prefix="/stocks", tags=["valuation"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

SUPPORTED_METRICS = ("PE", "EV_EBITDA", "PB", "PS")


class ValuationResponse(BaseModel):
    symbol: str
    method: str = "relative"
    metric: str
    peers: list[str]
    current: float
    peer_median: float
    margin_pct: float
    status: str
    computed_at: str


class ExplanationResponse(BaseModel):
    symbol: str
    explanation: str


def _default_metric(metric: str | None) -> str:
    if metric is None:
        return "PE"
    m = metric.upper()
    if m not in SUPPORTED_METRICS:
        raise ValidationError(
            "Unsupported metric value",
            {"metric": metric, "supported": list(SUPPORTED_METRICS)},
        )
    return m


@router.get("/{symbol}/valuation", response_model=ValuationResponse)
async def get_valuation(
    symbol: str,
    session: SessionDep,
    metric: str | None = Query(None),
) -> ValuationResponse:
    """Relative valuation vs industry peers for one metric (default P/E)."""
    m = _default_metric(metric)
    stock = await resolve_stock(session, symbol)
    result, peer_symbols = await analysis.compute_stock_valuation(
        session, stock, m
    )
    return ValuationResponse(
        symbol=result.symbol,
        metric=result.metric,
        peers=peer_symbols,
        current=result.current,
        peer_median=result.peer_median,
        margin_pct=result.margin_pct,
        status=result.status,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/{symbol}/valuation/explanation", response_model=ExplanationResponse)
async def get_valuation_explanation(
    symbol: str,
    session: SessionDep,
    metric: str | None = Query(None),
) -> ExplanationResponse:
    """Rule-based explanation of the relative-valuation result."""
    m = _default_metric(metric)
    stock = await resolve_stock(session, symbol)
    result, _ = await analysis.compute_stock_valuation(session, stock, m)
    return ExplanationResponse(
        symbol=result.symbol,
        explanation=explanation.valuation_explanation(result),
    )