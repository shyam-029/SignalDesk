# Alpha Score composite — quality/momentum/tone, with valuation kept separate.
#
# Methodology v1.5 (2026-09-08, owner decision):
#   composite = 40% fundamental + 35% technical + 25% sentiment
#   (news deprioritized from 30 to 25: FinBERT on headlines is the most
#   subjective pillar; technical raised from 30 to 35: price evidence is
#   the most objective daily signal.)
#   The FUNDAMENTAL pillar itself now blends the balance sheet:
#     fundamental = 45% profitability + 30% solvency + 25% Altman Z''
#     distress score (services/altman.distress_score_0_100), renormalized
#     over the components that have data. A stock with no stored balance
#     sheet scores on profitability/solvency alone — the missing diagnostic
#     never becomes a zero.
#   Weights renormalize over available components; bounded 0-100.
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
from app.services import altman as altman_svc
from app.services.valuation import InsufficientDataError, NoPeersError, ValuationResult

# Weights for the composite blend (v1.5).
W_FUNDAMENTAL = 0.40
W_TECHNICAL = 0.35
W_SENTIMENT = 0.25

# Fundamental pillar blend (v1.5): balance sheet enters via the Altman
# distress diagnostic; renormalized over available components.
FUND_PROFITABILITY = 0.45
FUND_SOLVENCY = 0.30
FUND_DISTRESS = 0.25


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

    # 1. Fundamental pillar v1.5: profitability + solvency + Altman distress,
    #    renormalized over what exists. The distress component reads the
    #    stored balance sheet (pure DB read; unavailable -> dropped, never 0).
    profitability: int | None = None
    solvency: int | None = None
    try:
        profit, solvency_score, _ = await analysis.compute_stock_scores(session, stock)
        profitability = profit.score
        solvency = solvency_score.score
    except InsufficientDataError:
        pass

    distress: int | None = None
    altman_result = await altman_svc.compute_stock_altman(session, stock)
    if altman_result.status == altman_svc.STATUS_AVAILABLE and altman_result.score is not None:
        distress = altman_svc.distress_score_0_100(altman_result.score)

    fundamental = blend_fundamental(profitability, solvency, distress)

    # 2. Technical = indicators over recent closes.
    technical: int | None = None
    technical_components: dict[str, float] = {}
    closes = await price_repo.get_close_series(session, stock.id, limit=200)
    if len(closes) >= 26:  # enough for SMA20 + MACD(26)
        tech = indicators.score_technicals(closes)
        technical = tech["score"]
        technical_components = tech["components"]
        if distress is not None:
            technical_components = {
                **technical_components,
                "distress": float(distress),
            }

    # 3. Sentiment = FinBERT aggregate mapped -1..+1 -> 0..100.
    sentiment: int | None = None
    summary = await news_repo.get_sentiment_summary(session, stock.symbol)
    if summary and summary["count"]:
        sentiment = round((summary["score"] + 1.0) / 2.0 * 100.0)

    # 4. Composite = 40/35/25 renormalized.
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


def blend_fundamental(
    profitability: int | None, solvency: int | None, distress: int | None
) -> int | None:
    """Blend the fundamental pillar (v1.5): profit .45 / solvency .30 /
    distress .25, renormalized over the components that have data.

    All-missing -> None; a missing diagnostic is dropped, never zero-filled.
    """
    pairs: list[tuple[float, float]] = []
    if profitability is not None:
        pairs.append((FUND_PROFITABILITY, float(profitability)))
    if solvency is not None:
        pairs.append((FUND_SOLVENCY, float(solvency)))
    if distress is not None:
        pairs.append((FUND_DISTRESS, float(distress)))
    if not pairs:
        return None
    total_w = sum(w for w, _ in pairs)
    return round(sum(w * v for w, v in pairs) / total_w)