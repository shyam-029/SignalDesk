# Grounded contextual explanations for /stocks/{symbol}/explain (Phase 6).
#
# Reuses the Phase 5 architecture (allow-list facts → prompt → LLMProvider,
# rule-based fallback, TTL cache, shared daily cap) but for QUESTION TYPES
# instead of a single composite score. This is NOT a chatbot: the caller picks
# one of five fixed question types, and the model only ever sees facts that
# SignalDesk explicitly allow-lists for that type.
#
# Security boundary mirrors llm_narrative.py:
#   gathered facts (router builds them explicitly, never from ORM __dict__)
#     |  _filter_facts()  <-- per-type allow-list (second boundary)
#     v
#   prompt
#
# Fallback chain (identical to /alpha): no key → no model → budget exhausted →
# provider LLMError — all fall back to the rule-based explanation. Never raises.

import json
import logging
import time
from datetime import date

from app.config import settings
from app.providers.llm_base import LLMError, LLMProvider, LLMResult
from app.providers.openrouter_provider import OpenRouterProvider
from app.services import llm_narrative  # shared daily-cap counter

logger = logging.getLogger(__name__)

# Fixed question types — anything else is a 422 at the router, never a prompt.
QUESTION_TYPES = ("alpha", "technical", "valuation", "fundamental", "sentiment")

# Per-type fact allow-lists. Keys outside these sets are stripped before any
# prompt is built, so adding a field to a facts dict is not enough to expose it.
_ALLOWED_FACT_KEYS: dict[str, set[str]] = {
    "alpha": {
        "symbol", "composite", "fundamental", "technical", "sentiment",
        "components", "weights", "insufficient_data", "value_signal",
        "available",
    },
    "technical": {
        "symbol", "score", "trend", "momentum", "reversion", "sma20", "ema12",
        "rsi14", "macd_histogram", "macd_signal", "last_close", "closes_used",
        "available",
    },
    "valuation": {
        "symbol", "metric", "current", "peer_median", "margin_pct", "status",
        "peer_count", "available",
    },
    "fundamental": {
        "symbol", "profitability", "solvency", "profitability_components",
        "solvency_components", "available",
    },
    "sentiment": {"symbol", "net_score", "label", "count", "available"},
}

# Same output contract as the /alpha narrative (short, grounded, no advice).
_OUTPUT_CONTRACT = (
    "Write a short explanation (at most 3 sentences, about 60-80 words) that "
    "narrates ONLY the facts provided. Do NOT invent any number or metric not "
    "given. Do NOT give investment advice (no buy/sell/hold recommendations). "
    "Do NOT make guaranteed future-return or price claims (e.g. 'will rise', "
    "'guaranteed', target prices). If the data is insufficient, say so plainly "
    "and do not speculate. End with a brief note that this is not investment advice."
)

_QUESTION_FRAMING = {
    "alpha": "Explain why the Alpha composite score is what it is.",
    "technical": "Explain the technical positioning and what drives its score.",
    "valuation": "Explain the relative-valuation conclusion versus industry peers.",
    "fundamental": "Explain what is driving the fundamental (profitability/solvency) scores.",
    "sentiment": "Explain the aggregate news sentiment and what it means.",
}

# In-process TTL cache, keyed (symbol, question_type, date).
_TTL_SECONDS = 24 * 60 * 60
_cache: dict[tuple[str, str, date], tuple[float, str]] = {}


def _filter_facts(question_type: str, facts: dict) -> dict:
    """Keep ONLY the allow-listed keys for this question type.

    Second security boundary: even if a caller stuffs extra keys into the
    facts dict, they never reach the prompt.
    """
    allowed = _ALLOWED_FACT_KEYS[question_type]
    return {k: v for k, v in facts.items() if k in allowed}


def build_prompt(question_type: str, facts: dict) -> tuple[str, str]:
    """Return (system, user) prompt messages for a contextual explanation."""
    framing = _QUESTION_FRAMING[question_type]
    system = f"Context: {framing}\n{_OUTPUT_CONTRACT}"
    user = json.dumps(_filter_facts(question_type, facts), indent=2, default=str)
    return system, user


def _fmt(value, suffix: str = "") -> str:
    """Format a fact for text output; missing values stay explicitly 'n/a'."""
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:g}{suffix}"
    return f"{value}{suffix}"


def _rule_based(question_type: str, facts: dict) -> str:
    """Deterministic explanation built from the same allow-listed facts.

    Always returns a useful sentence when the underlying data exists; says so
    plainly when it does not (no invented numbers, ever).
    """
    if not facts.get("available", False):
        return (
            "Insufficient data for this explanation: the underlying analysis "
            "could not be computed for this stock right now. This is not investment advice."
        )

    qt = question_type
    if qt == "alpha":
        parts = [f"Alpha composite {facts.get('composite')}/100"]
        for key, label in (("fundamental", "fundamentals"), ("technical", "technicals"),
                           ("sentiment", "sentiment")):
            if facts.get(key) is not None:
                parts.append(f"{label} {facts[key]}/100")
        vs = facts.get("value_signal")
        if vs:
            status = (vs.get("status") or "unknown").replace("_", " ")
            parts.append(
                f"Relative valuation {vs.get('metric') or 'PE'} margin "
                f"{_fmt(vs.get('margin_pct'))}% vs peers ({status})"
            )
        text = ". ".join(str(p) for p in parts) + "."
        if facts.get("insufficient_data"):
            text = "Insufficient data for a full Alpha composite. " + text
        return text + " This is not investment advice."

    if qt == "technical":
        return (
            f"Technical score {facts.get('score')}/100 over {facts.get('closes_used')} daily closes: "
            f"trend {facts.get('trend')}/100 (last close {_fmt(facts.get('last_close'))} vs SMA20 "
            f"{_fmt(facts.get('sma20'))}), momentum {facts.get('momentum')}/100 (MACD histogram "
            f"{_fmt(facts.get('macd_histogram'))}), mean reversion {facts.get('reversion')}/100 "
            f"(RSI14 {_fmt(facts.get('rsi14'))}). These are heuristic indicator readings, not a "
            "predictive model, and this is not investment advice."
        )

    if qt == "valuation":
        return (
            f"Relative valuation compares {facts.get('metric')} {_fmt(facts.get('current'))} against "
            f"the median {_fmt(facts.get('peer_median'))} of {facts.get('peer_count')} same-industry "
            f"peers: margin {_fmt(facts.get('margin_pct'))}% ({facts.get('status')}). Relatively "
            "cheaper than peers does not mean intrinsically cheap. This is not investment advice."
        )

    if qt == "fundamental":
        p, s = facts.get("profitability"), facts.get("solvency")
        strengths = [
            f"{c['name']} {c['value']}"
            for c in (facts.get("profitability_components") or []) + (facts.get("solvency_components") or [])
            if isinstance(c, dict) and c.get("score", 0) is not None and c.get("score", 0) >= 80
        ]
        text = f"Fundamental strength: profitability {p}/100, solvency {s}/100."
        if strengths:
            text += f" Strongest inputs: {', '.join(strengths[:3])}."
        return text + " This is not investment advice."

    if qt == "sentiment":
        return (
            f"Net news sentiment is {facts.get('label')} ({_fmt(facts.get('net_score'))} on a -1..+1 "
            f"scale) across {facts.get('count')} FinBERT-scored articles. This is not investment advice."
        )

    return "Insufficient data for this explanation. This is not investment advice."


def _log_usage(llm_result: LLMResult) -> None:
    tokens = llm_result.tokens_used if llm_result.tokens_used is not None else "n/a"
    logger.info(
        "llm_usage endpoint=explain tokens=%s model=%s explanation_len=%d",
        tokens, llm_result.model, len(llm_result.text),
    )


async def generate_explanation(
    question_type: str,
    facts: dict,
    provider: LLMProvider | None = None,
) -> str:
    """Return a grounded explanation for one question type, with fallbacks.

    Fallback triggers (in order): facts unavailable, no key/model configured,
    daily budget exhausted, provider LLMError. Never raises.
    """
    cache_key = (facts.get("symbol", ""), question_type, date.today())
    hit = _cache.get(cache_key)
    if hit and hit[0] > time.monotonic():
        logger.info("llm_cache hit symbol=%s question=%s", facts.get("symbol"), question_type)
        return hit[1]

    fallback = _rule_based(question_type, facts)

    # 1. Facts unavailable → rule-based "insufficient" text (no LLM spend).
    if not facts.get("available", False):
        _cache[cache_key] = (time.monotonic() + _TTL_SECONDS, fallback)
        return fallback

    # 2. LLM disabled (no key/model configured).
    if not settings.llm_api_key or not settings.llm_model:
        reason = "no_key" if not settings.llm_api_key else "no_model"
        logger.info("llm_disabled reason=%s question=%s", reason, question_type)
        _cache[cache_key] = (time.monotonic() + _TTL_SECONDS, fallback)
        return fallback

    # 3. Shared daily budget (same counter as /alpha).
    if not llm_narrative.budget_ok():
        logger.info("llm_skipped reason=budget_cap question=%s", question_type)
        _cache[cache_key] = (time.monotonic() + _TTL_SECONDS, fallback)
        return fallback

    # 4. Provider call; fall back on any LLMError.
    if provider is None:
        provider = OpenRouterProvider(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
    system, user = build_prompt(question_type, facts)
    try:
        llm_result = await provider.generate(system, user)
    except LLMError as exc:
        logger.warning("llm_fallback reason=provider_error question=%s error=%s", question_type, exc)
        _cache[cache_key] = (time.monotonic() + _TTL_SECONDS, fallback)
        return fallback

    llm_narrative.register_llm_call()
    _log_usage(llm_result)
    _cache[cache_key] = (time.monotonic() + _TTL_SECONDS, llm_result.text)
    return llm_result.text
