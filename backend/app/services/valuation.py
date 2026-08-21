# Relative (multiples) valuation — the approved methodology (PLANNING §8).
#
# Compare a stock's valuation multiple to the median of same-industry peers.
# Pure functions: no I/O, no DB, no HTTP. The repository (SP3) supplies the
# target's multiple and the peer multiple values; the router supplies nothing
# but the metric + data.
#
# Domain exceptions are defined HERE (service layer) per the approved design —
# they stay decoupled from FastAPI; routers map them to the error envelope.

from dataclasses import dataclass

from app.providers.base import Fundamentals

# Margin thresholds (%) for classification (PLANNING §8): outside these bands
# the stock is over/undervalued; inside it is "fairly valued".
UNDERVALUED_BELOW = -5.0
OVERVALUED_ABOVE = 5.0


class NoPeersError(Exception):
    """No comparable peer multiples were available. (routers map to 409)"""


class InsufficientDataError(Exception):
    """The target's multiple could not be computed. (routers map to 422/409)"""


@dataclass(frozen=True)
class ValuationResult:
    """The relative-valuation outcome for one metric."""

    symbol: str
    metric: str
    current: float
    peer_median: float
    peer_count: int
    margin_pct: float  # negative = undervalued
    status: str  # "undervalued" | "overvalued" | "fairly_valued"


METRIC_LABELS = {
    "PE": "P/E",
    "EV_EBITDA": "EV/EBITDA",
    "PB": "P/B",
    "PS": "P/S",
}


def compute_multiple(metric: str, f: Fundamentals) -> float | None:
    """Return the target's valuation multiple, or None if not computable.

    Higher/negative is meaningless for these multiples, so:
      - EV_EBITDA: None if EV or EBITDA missing, or EBITDA <= 0.
      - PE/PB/PS: the raw provider value (None propagates; caller filters).
    """
    if metric == "EV_EBITDA":
        ev = f.enterprise_value
        ebitda = f.ebitda
        if ev is None or ebitda is None or ebitda <= 0:
            return None
        return ev / ebitda
    if metric == "PE":
        return f.trailing_pe
    if metric == "PB":
        return f.price_to_book
    if metric == "PS":
        return f.price_to_sales
    raise ValueError(f"Unknown metric: {metric}")


def _median(values: list[float]) -> float:
    """Median; for an even count, the mean of the two middle values."""
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _is_valid(value: float | None) -> bool:
    """A peer multiple counts only if it is a finite positive number."""
    if value is None:
        return False
    try:
        return value == value and value > 0 and value not in (float("inf"), float("-inf"))
    except TypeError:
        return False


def relative_valuation(
    symbol: str, metric: str, current: float | None, peer_values: list[float | None]
) -> ValuationResult:
    """Compute the relative-valuation result for the target vs its peers.

    Args:
        symbol: target symbol (e.g. "RELIANCE.NS").
        metric: "PE" | "EV_EBITDA" | "PB" | "PS".
        current: the target's own multiple (None if not computable).
        peer_values: raw multiples of the peer set (may include None/negatives);
            the target is excluded defensively if present.

    Raises:
        InsufficientDataError: current is None/not positive.
        NoPeersError: no valid peer multiples remain.
    """
    if not _is_valid(current):
        raise InsufficientDataError(
            f"Cannot compute {metric} multiple for {symbol}"
        )

    peers = [v for v in peer_values if _is_valid(v)]

    if not peers:
        raise NoPeersError(f"No valid peers for {symbol} ({metric})")

    median = _median(peers)
    margin_pct = round((current / median - 1.0) * 100.0, 2)

    if margin_pct < UNDERVALUED_BELOW:
        status = "undervalued"
    elif margin_pct > OVERVALUED_ABOVE:
        status = "overvalued"
    else:
        status = "fairly_valued"

    return ValuationResult(
        symbol=symbol,
        metric=METRIC_LABELS.get(metric, metric),
        current=round(current, 2),
        peer_median=round(median, 2),
        peer_count=len(peers),
        margin_pct=margin_pct,
        status=status,
    )