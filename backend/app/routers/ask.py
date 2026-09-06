# POST /stocks/{symbol}/ask — grounded single-shot research question (Part H).
#
# NOT a chatbot: one free-text question per request, no conversation memory,
# no tool use, no database access from the model. The router gathers an
# evidence object EXPLICITLY (field by field, never from ORM __dict__) from
# the existing services; services/ask_narrative.py allow-lists it again,
# builds the prompt, validates the strict output contract, and falls back to
# a deterministic rule-based answer on every failure path.
#
# The user question is untrusted input: length-capped and sanitized, embedded
# in the prompt as quoted data, and additionally screened by OpenRouter's
# prompt-injection guardrail (a 403 from the provider maps to a safe
# ASK_BLOCKED error that exposes no guardrail details).

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import ValidationError
from app.routers.common import resolve_stock
from app.routers.history import PERFORMANCE_WINDOWS, _annualized_volatility_pct
from app.repositories import company_profiles as profile_repo
from app.repositories import financial_periods as fp_repo
from app.repositories import news as news_repo
from app.repositories import prices as price_repo
from app.services import alpha as alpha_svc
from app.services import analysis, indicators, llm_narrative
from app.services import ask_narrative as ask_svc
from app.services.valuation import InsufficientDataError, NoPeersError

router = APIRouter(prefix="/stocks", tags=["ask"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

MIN_CLOSES = 26
ANNUAL_PERIODS_INCLUDED = 5


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    symbol: str
    answer: str
    evidence: list[str]
    confidence: str
    source: str


def _round_or_none(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


async def _gather_evidence(session: AsyncSession, stock) -> dict:
    """Build the evidence object explicitly from existing services.

    Every field here is deliberate; ask_narrative.filter_evidence enforces the
    allow-list again before anything reaches a prompt.
    """
    evidence: dict = {"symbol": stock.symbol}

    evidence["company"] = {
        "name": stock.name,
        "sector": stock.sector,
        "industry": stock.industry,
    }

    # Provider-sourced company background (verbatim summary, leadership).
    # Lets the model answer "what does the company do / who is the CEO"
    # strictly from stored evidence; a summary that is not stored stays out.
    profile = await profile_repo.get_profile(session, stock.id)
    if profile is not None:
        evidence["company"]["business_summary"] = profile.business_summary
        evidence["company"]["ceo"] = profile.ceo
        evidence["company"]["employees"] = profile.employees
        evidence["company"]["website"] = profile.website

    # Latest quote (None-safe: a stock without bars carries no price block).
    latest_two = (await price_repo.get_two_latest(session, [stock.id])).get(stock.id, [])
    if latest_two:
        latest = latest_two[0]
        prev = latest_two[1] if len(latest_two) > 1 else None
        last = float(latest.close)
        price: dict = {
            "last_price": last,
            "open": float(latest.open),
            "high": float(latest.high),
            "low": float(latest.low),
            "volume": latest.volume,
            "date": latest.date.isoformat(),
        }
        if prev is not None and prev.close:
            prev_close = float(prev.close)
            price["prev_close"] = prev_close
            price["change_abs"] = round(last - prev_close, 2)
            price["change_pct"] = round((last - prev_close) / prev_close * 100, 2)
        evidence["price"] = price
        evidence["data_as_of"] = latest.date.isoformat()

    # Alpha composite + separate value signal (Phase 5 allow-listed shape).
    # A stock with no computable components carries no alpha block at all,
    # so the evidence-sufficiency check below sees the honest emptiness.
    alpha_result = await alpha_svc.compute_alpha(session, stock)
    if alpha_result.composite is not None:
        evidence["alpha"] = llm_narrative._alpha_facts(alpha_result)

    # Technical positioning (same math as /technicals).
    closes = await price_repo.get_close_series(session, stock.id, limit=200)
    if len(closes) >= MIN_CLOSES:
        scored = indicators.score_technicals(closes)
        comps = scored["components"]
        macd_vals = indicators.macd(closes)
        evidence["technical"] = {
            "score": scored["score"],
            "trend": comps.get("trend"),
            "momentum": comps.get("momentum"),
            "reversion": comps.get("reversion"),
            "sma20": _round_or_none(indicators.sma(closes, 20)),
            "ema12": _round_or_none(indicators.ema(closes, 12)),
            "rsi14": _round_or_none(indicators.rsi(closes, 14), 1),
            "macd": _round_or_none(macd_vals["histogram"]),
            "macd_signal": _round_or_none(macd_vals["signal"]),
            "last_close": closes[-1],
            "closes_used": len(closes),
        }

    # Relative valuation (P/E vs same-industry peers; None when incomputable).
    try:
        result, peers = await analysis.compute_stock_valuation(session, stock, "PE")
        evidence["valuation"] = {
            "metric": result.metric,
            "current": result.current,
            "peer_median": result.peer_median,
            "margin_pct": result.margin_pct,
            "status": result.status,
            "peer_count": len(peers),
        }
    except (NoPeersError, InsufficientDataError):
        pass

    # Fundamental scores (None when no snapshot).
    try:
        profit, solvency, _ = await analysis.compute_stock_scores(session, stock)
        evidence["fundamentals"] = {
            "profitability": profit.score,
            "solvency": solvency.score,
            "profitability_components": [
                {"name": c.name, "value": c.value, "score": c.score}
                for c in profit.components
            ],
            "solvency_components": [
                {"name": c.name, "value": c.value, "score": c.score}
                for c in solvency.components
            ],
        }
    except InsufficientDataError:
        pass

    # Windowed performance + 52-week range + volatility (same math as /performance).
    bars = await price_repo.get_bars(session, stock.id)
    if bars:
        as_of = bars[-1].date
        last_close = float(bars[-1].close)
        windows: dict = {}
        for label, days in PERFORMANCE_WINDOWS.items():
            target = as_of - timedelta(days=days)
            start_bar = None
            for bar in bars:
                if bar.date <= target:
                    start_bar = bar
                else:
                    break
            if start_bar is None or not start_bar.close:
                continue
            start_close = float(start_bar.close)
            windows[label] = {
                "change_pct": round((last_close - start_close) / start_close * 100, 2),
                "start_date": start_bar.date.isoformat(),
            }
        cutoff = as_of - timedelta(days=366)
        recent = [b for b in bars if b.date >= cutoff]
        evidence["performance"] = {
            "windows": windows,
            "high_52w": max((float(b.high) for b in recent), default=None),
            "low_52w": min((float(b.low) for b in recent), default=None),
            "volatility_1y_pct": _annualized_volatility_pct(
                [float(b.close) for b in recent]
            ),
            "as_of": as_of.isoformat(),
        }

    # News sentiment aggregate.
    summary = await news_repo.get_sentiment_summary(session, stock.symbol)
    if summary:
        evidence["sentiment"] = {
            "net_score": summary["score"],
            "label": summary["label"],
            "count": summary["count"],
        }

    # Historical financials (most recent five annual periods).
    periods = await fp_repo.get_periods(session, stock.id, period_type="annual")
    if periods:
        evidence["financial_history"] = [
            {
                "period_end": p.period_end.isoformat(),
                "period_type": p.period_type,
                "revenue": float(p.revenue) if p.revenue is not None else None,
                "net_income": float(p.net_income) if p.net_income is not None else None,
                "operating_margin": float(p.operating_margin)
                if p.operating_margin is not None
                else None,
                "net_margin": float(p.net_margin) if p.net_margin is not None else None,
                "eps": float(p.eps) if p.eps is not None else None,
            }
            for p in periods[:ANNUAL_PERIODS_INCLUDED]
        ]

    # Static methodology (how SignalDesk computes what the evidence shows).
    evidence["methodology"] = ask_svc._METHODOLOGY_TEXT

    return evidence


@router.post("/{symbol}/ask", response_model=AskResponse)
async def ask_stock(symbol: str, body: AskRequest, session: SessionDep) -> AskResponse:
    """One grounded question about this stock's computed research data."""
    question = ask_svc.sanitize_question(body.question)
    if not question:
        raise ValidationError(
            "Question must not be empty",
            {"question": "required"},
        )
    if len(body.question) > ask_svc.QUESTION_MAX_CHARS:
        # Measure the RAW input: sanitization must not become a way to accept
        # an oversized question that merely trims back under the cap.
        raise ValidationError(
            f"Question must be at most {ask_svc.QUESTION_MAX_CHARS} characters",
            {"question": "too_long", "max_chars": ask_svc.QUESTION_MAX_CHARS},
        )

    stock = await resolve_stock(session, symbol)
    evidence = await _gather_evidence(session, stock)

    try:
        result = await ask_svc.generate_ask_response(stock.symbol, question, evidence)
    except ask_svc.AskBlocked:
        # OpenRouter's prompt-injection guardrail (or an equivalent provider
        # policy) rejected the request. Safe, generic message; no details.
        raise ValidationError(
            "This question was blocked by safety filters. Rephrase it as a "
            "question about the stock's research data.",
            {"code": "ASK_BLOCKED"},
        )

    return AskResponse(
        symbol=stock.symbol,
        answer=result["answer"],
        evidence=result["evidence"],
        confidence=result["confidence"],
        source=result["source"],
    )
