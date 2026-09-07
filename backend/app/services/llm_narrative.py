# Grounded LLM narrative for the Alpha Score (/alpha only).
#
# Security boundary (approved Phase 5 plan):
#   AlphaResult
#     |  _alpha_facts()  <-- explicit allow-list (never result.__dict__)
#     v
#   serialized facts dict
#     |  build_alpha_prompt()
#     v
#   LLM prompt
#
# Only allow-listed facts ever reach the prompt, so a future free-text field on
# AlphaResult cannot become an instruction/data injection path.
#
# Placement note: these functions live here (not explanation.py) because
# explanation.py is already imported by analysis.py -> alpha.py; importing
# AlphaResult there would create a circular import. The rule-based fallback for
# /scores and /valuation stays in explanation.py untouched.

import json
import logging
import time
from datetime import date

from app.config import settings
from app.models import Stock
from app.providers.llm_base import LLMError, LLMResult, LLMProvider
from app.providers.openrouter_provider import OpenRouterProvider
from app.services.alpha import AlphaResult

logger = logging.getLogger(__name__)

# Output contract (also enforced in the prompt). We do NOT run a second model to
# police output; the prompt boundary plus these tests are the guardrail.
_OUTPUT_CONTRACT = (
    "Write a short explanation (at most 3 sentences, about 60-80 words) that "
    "narrates ONLY the facts provided. Do NOT invent any number or metric not "
    "given. Do NOT give investment advice (no buy/sell/hold recommendations). "
    "Do NOT make guaranteed future-return or price claims (e.g. 'will rise', "
    "'guaranteed', target prices). If the data is insufficient, say so plainly "
    "and do not speculate. End with a brief note that this is not investment advice."
)

# In-process TTL cache: key = (symbol, snapshot_date) ->
# (expires_at, narrative, source) where source is "llm" or "rule_based".
_TTL_SECONDS = 24 * 60 * 60  # cache within a day; Redis stays deferred.
_cache: dict[tuple[str, date], tuple[float, str, str]] = {}

# In-process daily budget counter.
_calls_today = 0
_calls_day = date.today()


def _alpha_facts(result: AlphaResult) -> dict:
    """Serialize ONLY the approved Alpha fields (allow-list, never asdict()).

    Additions require an explicit line here; a new AlphaResult field is not
    exposed to the LLM until deliberately allow-listed.
    """
    facts: dict = {
        "symbol": result.symbol,
        "composite": result.composite,
        "fundamental": result.fundamental,
        "technical": result.technical,
        "sentiment": result.sentiment,
        "components": dict(result.components),  # trend/momentum/reversion
        "weights": dict(result.weights),
        "insufficient_data": result.insufficient_data,
    }
    if result.value_signal is not None:
        # Only the structured fields; NOT value_signal.explanation (free text).
        facts["value_signal"] = {
            "metric": result.value_signal.metric,
            "status": result.value_signal.status,
            "margin_pct": result.value_signal.margin_pct,
        }
    else:
        facts["value_signal"] = None
    return facts


def build_alpha_prompt(result: AlphaResult) -> tuple[str, str]:
    """Return (system, user) prompt messages for the Alpha narrative.

    The system message carries the output contract; the user message carries
    only allow-listed facts.
    """
    system = _OUTPUT_CONTRACT
    user = json.dumps(_alpha_facts(result), indent=2, default=str)
    return system, user


def _alpha_narrative(result: AlphaResult) -> str:
    """Rule-based fallback narrative — no LLM, always available.

    Builds a plain-text explanation from the same allow-listed facts.
    """
    parts: list[str] = []
    if result.insufficient_data or result.composite is None:
        parts.append("Insufficient data to form an Alpha composite.")
    else:
        parts.append(f"Alpha composite {result.composite}/100")
        if result.fundamental is not None:
            parts.append(f"fundamentals {result.fundamental}/100")
        if result.technical is not None:
            parts.append(f"technicals {result.technical}/100")
        if result.sentiment is not None:
            parts.append(f"sentiment {result.sentiment}/100")
    if result.value_signal is not None:
        vs = result.value_signal
        status = (vs.status or "unknown").replace("_", " ")
        parts.append(
            f"Valuation {vs.metric or 'PE'} margin {vs.margin_pct or 'n/a'}% vs peers ({status})"
        )
    return ". ".join(parts) + "."


def _budget_ok() -> bool:
    """True if the in-process daily call budget is not exhausted."""
    global _calls_day, _calls_today
    today = date.today()
    if today != _calls_day:
        _calls_day = today
        _calls_today = 0
    return _calls_today < settings.llm_daily_cap


def budget_ok() -> bool:
    """Public wrapper so other grounded endpoints share the SAME daily cap."""
    return _budget_ok()


def register_llm_call() -> None:
    """Count one provider call against the shared in-process daily budget."""
    global _calls_today
    _calls_today += 1


def _log_usage(llm_result: LLMResult) -> None:
    """Record token/model usage (None-safe) so cost is visible in logs."""
    tokens = llm_result.tokens_used if llm_result.tokens_used is not None else "n/a"
    logger.info(
        "llm_usage tokens=%s model=%s explanation_len=%d",
        tokens,
        llm_result.model,
        len(llm_result.text),
    )


# Narrative provenance: "llm" when a provider call produced the text,
# "rule_based" for every deterministic-fallback path. Exposed on
# GET /alpha/explanation so fallback is observable (Phase 7).
SOURCE_LLM = "llm"
SOURCE_RULE = "rule_based"


async def generate_alpha_explanation_result(
    stock: Stock,
    result: AlphaResult,
    provider: LLMProvider | None = None,
) -> tuple[str, str]:
    """Return (narrative, source), falling back to the rule-based narrative.

    Fallback triggers (in order): no key or no model configured, budget
    exhausted, provider raises LLMError. Never raises; always returns.

    `provider` is injectable for tests; when None, one is built from settings.
    """
    # 1. TTL cache: reuse today's narrative if present.
    cache_key = (stock.symbol, date.today())
    hit = _cache.get(cache_key)
    if hit and hit[0] > time.monotonic():
        logger.info("llm_cache hit symbol=%s", stock.symbol)
        return hit[1], hit[2]

    # 2. Short-circuit if LLM is disabled (no key/model) or budget exhausted.
    if not settings.llm_api_key or not settings.llm_model:
        reason = "no_key" if not settings.llm_api_key else "no_model"
        logger.info("llm_disabled reason=%s symbol=%s", reason, stock.symbol)
        narrative = _alpha_narrative(result)
        _cache[cache_key] = (time.monotonic() + _TTL_SECONDS, narrative, SOURCE_RULE)
        return narrative, SOURCE_RULE

    if not _budget_ok():
        logger.info("llm_skipped reason=budget_cap symbol=%s", stock.symbol)
        narrative = _alpha_narrative(result)
        _cache[cache_key] = (time.monotonic() + _TTL_SECONDS, narrative, SOURCE_RULE)
        return narrative, SOURCE_RULE

    # 3. Call the provider; on failure fall back to the rule-based narrative.
    if provider is None:
        provider = OpenRouterProvider(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
    system, user = build_alpha_prompt(result)
    t0 = time.perf_counter()
    try:
        llm_result = await provider.generate(system, user)
    except LLMError as exc:
        duration_ms = round((time.perf_counter() - t0) * 1000)
        logger.warning(
            "llm_fallback reason=provider_error symbol=%s duration_ms=%d error=%s",
            stock.symbol, duration_ms, exc,
        )
        narrative = _alpha_narrative(result)
        _cache[cache_key] = (time.monotonic() + _TTL_SECONDS, narrative, SOURCE_RULE)
        return narrative, SOURCE_RULE

    register_llm_call()
    duration_ms = round((time.perf_counter() - t0) * 1000)
    _log_usage(llm_result)
    logger.info(
        "llm_success symbol=%s duration_ms=%d", stock.symbol, duration_ms
    )
    narrative = llm_result.text
    _cache[cache_key] = (time.monotonic() + _TTL_SECONDS, narrative, SOURCE_LLM)
    return narrative, SOURCE_LLM


async def generate_alpha_explanation(
    stock: Stock,
    result: AlphaResult,
    provider: LLMProvider | None = None,
) -> str:
    """Text-only wrapper (kept for the nightly pre-warm and older callers)."""
    narrative, _source = await generate_alpha_explanation_result(
        stock, result, provider
    )
    return narrative