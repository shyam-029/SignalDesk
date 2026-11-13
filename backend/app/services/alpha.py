# Alpha Score composite: business, price strength and news tone, with
# valuation kept separate.
#
# Methodology v2.0 (2026-11-14, owner decision "swap now"):
#   composite = 40% fundamental + 35% strength + 25% sentiment
#   The price pillar is now Strength (services/strength.py): the stock's
#   one-year price strength ranked against the rest of the list. It replaced
#   the technical score (trend/momentum/reversion over the last few weeks),
#   which a twelve-year test found had no edge: its top fifth trailed the
#   average share after costs, while Strength's top fifth beat it by about
#   0.7% a month, also in the years held back. The technical score is still
#   computed and shown on its own, but no longer feeds the composite.
#   Strength is a rank over the whole list, so it is computed once a night
#   (jobs.record_strength_scores) and read back here.
#
# v1.5 (2026-09-08): 40% fundamental + 35% technical + 25% sentiment.
#
# The FUNDAMENTAL pillar blends the balance sheet:
#   fundamental = 45% profitability + 30% solvency + 25% Altman Z''
#   distress score (services/altman.distress_score_0_100), renormalized
#   over the components that have data. A missing component is dropped,
#   never scored as zero.
# Weights renormalize over available pillars; bounded 0-100.
# Valuation is NOT blended in; it is surfaced separately as value_signal
# (multiples already derive from fundamentals).
#
# Pure computation lives here; data loading is delegated to the existing
# services/repositories (analysis.compute_stock_scores, indicators, news repo,
# strength repo).

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Stock
from app.repositories import news as news_repo
from app.repositories import prices as price_repo
from app.repositories import strength as strength_repo
from app.services import analysis, indicators
from app.services import strength as strength_svc
from app.services import altman as altman_svc
from app.services.valuation import InsufficientDataError, NoPeersError, ValuationResult

METHODOLOGY_VERSION = "2.0"

# Weights for the composite blend (v2.0).
W_FUNDAMENTAL = 0.40
W_STRENGTH = 0.35
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
    # Shown on its own; not part of the composite since v2.0.
    technical: int | None
    # The composite's price pillar (0-100 rank), None when not rated.
    strength: int | None
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
    fundamental: float | None,
    strength: float | None,
    sentiment: float | None,
) -> tuple[int | None, dict[str, float]]:
    """Weighted blend with weights renormalized over available pillars."""
    named: list[tuple[str, float, float]] = []
    if fundamental is not None:
        named.append(("fundamental", W_FUNDAMENTAL, float(fundamental)))
    if strength is not None:
        named.append(("strength", W_STRENGTH, float(strength)))
    if sentiment is not None:
        named.append(("sentiment", W_SENTIMENT, float(sentiment)))

    if not named:
        return None, {}

    total_w = sum(w for _, w, _ in named)
    composite = sum(w * v for _, w, v in named) / total_w
    weights = {name: round(w / total_w, 2) for name, w, _ in named}
    return round(composite), weights


async def stored_strength(session: AsyncSession, symbol: str, last_bar) -> int | None:
    """The stock's newest nightly Strength rank, if it is current.

    None when the stock was never rated, or when its newest rating is more
    than strength_svc.STALE_DAYS older than its latest bar (the last pass
    left it unrated: short history, a stale bar or a suspect move).
    """
    stored = await strength_repo.get_latest_rating(session, symbol)
    if stored is None:
        return None
    as_of, values = stored
    value = values.get(strength_repo.KEY_STRENGTH)
    if value is None:
        return None
    if last_bar is not None and (last_bar - as_of).days > strength_svc.STALE_DAYS:
        return None
    return round(float(value))


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

    # 2. Technical = indicators over recent closes (shown, not blended).
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

    # 4. Strength = the nightly list-wide rank, read back.
    last_bar = await price_repo.get_latest_date(session, stock.id)
    strength = await stored_strength(session, stock.symbol, last_bar)

    # 5. Composite = 40/35/25 renormalized.
    composite, weights = _renormalized(fundamental, strength, sentiment)

    # 6. Value signal (separate) — valuation must not fail the request.
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
        strength=strength,
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