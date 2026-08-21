# Rule-based explanations (D6): build human-readable text from the ACTUAL
# computed components — no ML model, no LLM (that's a later phase).

from app.services.scores import ComponentScore
from app.services.valuation import ValuationResult


def profitability_explanation(cs: ComponentScore) -> str:
    """Explain a profitability score from its real components."""
    if not cs.available:
        return "Insufficient data to compute a profitability score."
    parts = ", ".join(
        f"{c.name} {c.value:.1f}% ({c.score:.0f}/100)" for c in cs.components
    )
    return f"Profitability {cs.score}/100: {parts}."


def solvency_explanation(cs: ComponentScore) -> str:
    """Explain a solvency score from its real components."""
    if not cs.available:
        return "Insufficient data to compute a solvency score."

    def _fmt(c) -> str:
        # D/E and ratios aren't percentages; format them as plain numbers.
        print_value = c.value
        return f"{c.name} {print_value:.2f} ({c.score:.0f}/100)"

    parts = ", ".join(_fmt(c) for c in cs.components)
    return f"Solvency {cs.score}/100: {parts}."


def valuation_explanation(v: ValuationResult) -> str:
    """Explain a relative-valuation result in one sentence."""
    direction = {
        "undervalued": "undervalued",
        "overvalued": "overvalued",
        "fairly_valued": "fairly valued",
    }[v.status]
    return (
        f"{v.symbol} trades at {v.metric} {v.current} vs an industry median of "
        f"{v.peer_median} — {direction} by {abs(v.margin_pct):.1f}%."
    )