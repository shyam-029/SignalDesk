# Alpha Score composite — quality/momentum/tone, with valuation kept separate.
#
# Methodology (approved Phase 4 plan):
#   composite = 40% fundamental + 30% technical + 30% sentiment
#   weights renormalized over available components; bounded 0-100.
#   Valuation is NOT blended in — surfaced separately as value_signal
#   (avoids double-counting: multiples already derive from fundamentals).
#
# Pure computation lives here; data loading is delegated to the existing
# services/repositories (analysis.compute_stock_scores, indicators, news repo).

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Stock
from app.repositories import news as news_repo
from app.repositories import prices as price_repo
from app.services import analysis, indicators
from app.services.valuation import InsufficientDataError, NoPeersError, ValuationResult

# Weights for the composite blend.
W_FUNDAMENTAL = 0.40
W_TECHNICAL = 0.30
W_SENTIMENT = 0.30


@dataclass(frozen=True)
class ValueSignal:
    """Cheap/expensive read, computed from relative valuation (kept separate)."""

    metric: str | None
    status: str | None
    margin_pct: float | None
    explanation: str | None


@dataclass(frozen=True)
class AlphaResult:
    symbol: str
    composite: int | None
    fundamental: int | None
    technical: int | None
    sentiment: int | None
    components: dict[str, float]  # technical sub-scores (trend/momentum/reversion)
    weights: dict[str, float]  # renormalized composite weights
    value_signal: ValueSignal | None
    insufficient_data: bool


def _mean_of(score_a: int | None, score_b: int | None) -> int | None:
    """Mean of two 0-100 scores; a missing one is dropped."""
    vals = [v for v in (score_a, score_b) if v is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals))


def _renormalized(
    fundamental: int | None,
    technical: int | None,
    sentiment: int | None,
) -> tuple[int | None, dict[str, float]]:
    """Weighted blend with weights renormalized over available components."""
    pairs: list[tuple[float, float]] = []
    if fundamental is not None:
        pairs.append((W_FUNDAMENTAL, float(fundamental)))
    if technical is not None:
        pairs.append((W_TECHNICAL, float(technical)))
    if sentiment is not None:
        pairs.append((W_SENTIMENT, float(sentiment)))

    if not pairs:
        return None, {}

    total_w = sum(w for w, _ in pairs)
    composite = sum(w * s for w, s in pairs) / total_w
    weights = {k: round(v, 2) for k, v in zip(
        ["fundamental", "technical", "sentiment"],
        [w / total_w for w, _ in pairs],
    )}
    return round(composite), weights


async def compute_alpha(session: AsyncSession, stock: Stock) -> AlphaResult:
    """Compute the Alpha Score composite for one stock (and its value signal)."""

    # 1. Fundamental = mean(profitability, solvency) — reuse analysis service.
    fundamental: int | None = None
    try:
        profit, solvency, _ = await analysis.compute_stock_scores(session, stock)
        fundamental = _mean_of(profit.score, solvency.score)
    except InsufficientDataError:
        fundamental = None

    # 2. Technical = indicators over recent closes.
    technical: int | None = None
    technical_components: dict[str, float] = {}
    closes = await price_repo.get_close_series(session, stock.id, limit=200)
    if len(closes) >= 26:  # enough for SMA20 + MACD(26)
        tech = indicators.score_technicals(closes)
        technical = tech["score"]
        technical_components = tech["components"]

    # 3. Sentiment = FinBERT aggregate mapped -1..+1 -> 0..100.
    sentiment: int | None = None
    summary = await news_repo.get_sentiment_summary(session, stock.symbol)
    if summary and summary["count"]:
        sentiment = round((summary["score"] + 1.0) / 2.0 * 100.0)

    # 4. Composite = 40/30/30 renormalized.
    composite, weights = _renormalized(fundamental, technical, sentiment)

    # 5. Value signal (separate) — valuation must not fail the request.
    value_signal = None
    try:
        result: ValuationResult
        peers: list[str]
        result, _ = await analysis.compute_stock_valuation(session, stock, "PE")
        value_signal = ValueSignal(
            metric=result.metric,
            status=result.status,
            margin_pct=result.margin_pct,
            explanation=(
                f"Trades at {result.metric} {result.current} vs industry median "
                f"{result.peer_median} ({result.status})."
            ),
        )
    except (NoPeersError, InsufficientDataError):
        value_signal = None

    return AlphaResult(
        symbol=stock.symbol,
        composite=composite,
        fundamental=fundamental,
        technical=technical,
        sentiment=sentiment,
        components=technical_components,
        weights=weights,
        value_signal=value_signal,
        insufficient_data=composite is None,
    )