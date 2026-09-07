# Alpha Score endpoint — composite + separate value signal.
#
# Part I split: GET /alpha returns ONLY computed data (composite, components,
# weights, value signal) — zero LLM work, so the score renders the moment the
# DB math finishes. The narrative moved to GET /alpha/explanation (same rule-
# based + LLM-with-fallback pipeline, TTL-cached, pre-warmed nightly by the
# ingestion sweep), which the frontend fetches in parallel and renders in its
# own region.

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.repositories import alpha as alpha_repo
from app.routers.common import resolve_stock
from app.services import alpha as alpha_svc
from app.services.llm_narrative import generate_alpha_explanation_result

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


class AlphaExplanationResponse(BaseModel):
    symbol: str
    explanation: str
    # Provenance of the text: "llm" or "rule_based" (fallback is observable).
    source: str


@router.get("/{symbol}/alpha", response_model=AlphaResponse)
async def get_alpha(symbol: str, session: SessionDep) -> AlphaResponse:
    """Alpha Score composite (quality/momentum/tone) + separate value signal.

    Pure computation: no LLM work happens on this path.
    """
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


@router.get("/{symbol}/alpha/explanation", response_model=AlphaExplanationResponse)
async def get_alpha_explanation(
    symbol: str, session: SessionDep
) -> AlphaExplanationResponse:
    """Written explanation for the Alpha Score (lazy, cache-first).

    Same grounding pipeline as before: allow-listed facts, LLM if configured,
    rule-based fallback otherwise, TTL cache shared with the nightly
    pre-warm sweep. The /alpha compute path never waits on this.
    """
    stock = await resolve_stock(session, symbol)
    result = await alpha_svc.compute_alpha(session, stock)
    explanation, source = await generate_alpha_explanation_result(stock, result)
    return AlphaExplanationResponse(
        symbol=stock.symbol, explanation=explanation, source=source
    )
