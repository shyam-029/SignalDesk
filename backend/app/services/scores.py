# Fundamental score computation — the approved methodology (PLANNING §8b).
#
# Fixed-threshold piecewise-linear mapping. One helper implements every metric:
#   higher-is-better:  100 * clamp((value - F) / (C - F), 0, 1)
#   lower-is-better:   100 * clamp((F - value) / (F - C), 0, 1)
# where F = floor (value that yields 0 points), C = ceiling (value that yields
# 100 points). This single formula naturally handles boundaries and negatives
# (negative ROE -> below floor -> 0; negative D/E -> above ceiling -> 100).
#
# Missing metrics: dropped and the remaining weights are renormalized. If all
# components are missing the score is None with available=False.
#
# Input normalization: ROE/ROA/margins arrive from the provider as DECIMALS
# (0.18 = 18%), so they are scaled by 100 before scoring. D/E is already a
# percent; interest-coverage and current-ratio are plain ratios.

from dataclasses import dataclass
from typing import Callable

from app.providers.base import Fundamentals


@dataclass(frozen=True)
class Component:
    """One scored metric: name, normalized value, and its 0-100 score."""

    name: str
    value: float  # normalized (percents for the %-based metrics)
    score: float  # 0-100


@dataclass(frozen=True)
class ComponentScore:
    """The result of scoring a group: overall 0-100 score + per-metric detail."""

    score: int | None  # None when no components were available
    components: list[Component]
    available: bool


# --- Metric table -----------------------------------------------------------
# Each entry: (name, field, weight, floor, ceiling, higher_is_better, scale).
PROFITABILITY_METRICS: list[tuple[str, str, float, float, float, bool, float]] = [
    ("ROE", "return_on_equity", 0.40, 0.0, 20.0, True, 100.0),
    ("ROA", "return_on_assets", 0.20, 0.0, 12.0, True, 100.0),
    ("Operating margin", "operating_margin", 0.20, 0.0, 25.0, True, 100.0),
    ("Net margin", "profit_margin", 0.20, 0.0, 20.0, True, 100.0),
]

SOLVENCY_METRICS: list[tuple[str, str, float, float, float, bool, float]] = [
    ("Debt/Equity", "debt_to_equity", 0.50, 200.0, 50.0, False, 1.0),
    ("Interest coverage", "interest_coverage", 0.30, 1.0, 5.0, True, 1.0),
    ("Current ratio", "current_ratio", 0.20, 0.5, 2.0, True, 1.0),
]


def _linear(
    value: float, floor: float, ceiling: float, higher_is_better: bool
) -> float:
    """Map a value to a 0-100 score via the piecewise-linear formula."""
    if higher_is_better:
        ratio = (value - floor) / (ceiling - floor)
    else:
        ratio = (floor - value) / (floor - ceiling)
    clamped = min(max(ratio, 0.0), 1.0)
    return 100.0 * clamped


def _score_group(
    fundamentals: Fundamentals,
    metrics: list[tuple[str, str, float, float, float, bool, float]],
) -> ComponentScore:
    """Score a metric group, renormalizing weights over available metrics."""
    components: list[Component] = []
    weights: list[float] = []
    scores: list[float] = []

    for name, field, weight, floor, ceiling, higher, scale in metrics:
        raw = getattr(fundamentals, field)
        if raw is None:
            continue
        value = raw * scale
        s = _linear(value, floor, ceiling, higher)
        components.append(Component(name=name, value=value, score=round(s, 1)))
        weights.append(weight)
        scores.append(s)

    if not components:
        return ComponentScore(score=None, components=[], available=False)

    total_weight = sum(weights)
    weighted_sum = sum(w * s for w, s in zip(weights, scores)) / total_weight
    return ComponentScore(
        score=round(weighted_sum),
        components=components,
        available=True,
    )


def profitability_score(fundamentals: Fundamentals) -> ComponentScore:
    """Compute the 0-100 profitability score per §8b."""
    return _score_group(fundamentals, PROFITABILITY_METRICS)


def solvency_score(fundamentals: Fundamentals) -> ComponentScore:
    """Compute the 0-100 solvency score per §8b."""
    return _score_group(fundamentals, SOLVENCY_METRICS)