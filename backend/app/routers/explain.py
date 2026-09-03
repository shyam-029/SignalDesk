# POST /stocks/{symbol}/explain — grounded contextual explanations (Phase 6).
#
# Five FIXED question types (alpha/technical/valuation/fundamental/sentiment).
# This is not a chatbot: there is no free-text question — the caller selects a
# type, the router gathers allow-listed facts from the existing services, and
# services/explain_narrative.py narrates them (LLM if configured, rule-based
# fallback otherwise). Every failure path degrades to a useful rule-based text.
#
# Facts are built here EXPLICITLY (field by field, never from ORM __dict__),
# then filtered again by the per-type allow-list inside the narrative service.

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import ValidationError
from app.routers.common import resolve_stock
from app.repositories import news as news_repo
from app.repositories import prices as price_repo
from app.services import alpha as alpha_svc
from app.services import analysis, indicators
from app.services import explain_narrative as narr
from app.services import llm_narrative
from app.services.valuation import InsufficientDataError, NoPeersError

router = APIRouter(prefix="/stocks", tags=["explain"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Same threshold as /alpha and /technicals: enough for SMA20 + MACD(26).
MIN_CLOSES = 26


class ExplainRequest(BaseModel):
    question_type: str


class ExplainResponse(BaseModel):
    symbol: str
    question_type: str
    explanation: str


def _component_rows(components) -> list[dict]:
    """Explicitly serialize score components (never pass ORM/dataclass directly)."""
    return [{"name": c.name, "value": c.value, "score": c.score} for c in components]


async def _gather_facts(session: AsyncSession, stock, question_type: str) -> dict:
    """Collect allow-listed facts for one question type from existing services.

    Missing underlying data → available=False (never fabricated).
    """
    if question_type == "alpha":
        # Reuse the EXACT Phase 5 allow-list serialization for Alpha facts.
        result = await alpha_svc.compute_alpha(session, stock)
        facts = dict(llm_narrative._alpha_facts(result))
        facts["available"] = True
        return facts

    if question_type == "technical":
        closes = await price_repo.get_close_series(session, stock.id, limit=200)
        if len(closes) < MIN_CLOSES:
            return {"symbol": stock.symbol, "available": False, "closes_used": len(closes)}
        scored = indicators.score_technicals(closes)
        comps = scored["components"]
        macd_vals = indicators.macd(closes)
        return {
            "symbol": stock.symbol,
            "available": True,
            "score": scored["score"],
            "trend": comps.get("trend"),
            "momentum": comps.get("momentum"),
            "reversion": comps.get("reversion"),
            "sma20": indicators.sma(closes, 20),
            "ema12": indicators.ema(closes, 12),
            "rsi14": indicators.rsi(closes, 14),
            "macd_histogram": macd_vals["histogram"],
            "macd_signal": macd_vals["signal"],
            "last_close": closes[-1],
            "closes_used": len(closes),
        }

    if question_type == "valuation":
        try:
            result, peers = await analysis.compute_stock_valuation(session, stock, "PE")
        except (NoPeersError, InsufficientDataError):
            return {"symbol": stock.symbol, "available": False}
        return {
            "symbol": stock.symbol,
            "available": True,
            "metric": result.metric,
            "current": result.current,
            "peer_median": result.peer_median,
            "margin_pct": result.margin_pct,
            "status": result.status,
            "peer_count": len(peers),
        }

    if question_type == "fundamental":
        try:
            profit, solvency, _ = await analysis.compute_stock_scores(session, stock)
        except InsufficientDataError:
            return {"symbol": stock.symbol, "available": False}
        return {
            "symbol": stock.symbol,
            "available": True,
            "profitability": profit.score,
            "solvency": solvency.score,
            "profitability_components": _component_rows(profit.components),
            "solvency_components": _component_rows(solvency.components),
        }

    if question_type == "sentiment":
        summary = await news_repo.get_sentiment_summary(session, stock.symbol)
        if summary is None:
            return {"symbol": stock.symbol, "available": False}
        return {
            "symbol": stock.symbol,
            "available": True,
            "net_score": summary["score"],
            "label": summary["label"],
            "count": summary["count"],
        }

    raise ValidationError(
        "Unsupported question type",
        {"question_type": question_type, "supported": list(narr.QUESTION_TYPES)},
    )


@router.post("/{symbol}/explain", response_model=ExplainResponse)
async def explain_stock(
    symbol: str, body: ExplainRequest, session: SessionDep
) -> ExplainResponse:
    """Grounded explanation for a fixed question type about one stock."""
    if body.question_type not in narr.QUESTION_TYPES:
        raise ValidationError(
            "Unsupported question type",
            {
                "question_type": body.question_type,
                "supported": list(narr.QUESTION_TYPES),
            },
        )

    stock = await resolve_stock(session, symbol)
    facts = await _gather_facts(session, stock, body.question_type)
    explanation = await narr.generate_explanation(body.question_type, facts)

    return ExplainResponse(
        symbol=stock.symbol,
        question_type=body.question_type,
        explanation=explanation,
    )
