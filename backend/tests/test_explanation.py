# Unit tests for the rule-based explanation service (D6). Pure functions.

from app.providers.base import Fundamentals
from app.services.explanation import (
    profitability_explanation,
    solvency_explanation,
    valuation_explanation,
)
from app.services.scores import profitability_score, solvency_score
from app.services.valuation import relative_valuation


def test_profitability_explanation_reflects_components():
    f = Fundamentals(symbol="X", return_on_equity=0.18, operating_margin=0.125)
    cs = profitability_score(f)
    text = profitability_explanation(cs)
    assert text.startswith("Profitability ")
    assert "ROE 18.0%" in text
    assert "Operating margin 12.5%" in text


def test_profitability_explanation_insufficient_data():
    cs = profitability_score(Fundamentals(symbol="X"))
    assert profitability_explanation(cs) == (
        "Insufficient data to compute a profitability score."
    )


def test_solvency_explanation_reflects_components():
    f = Fundamentals(symbol="X", debt_to_equity=50.0, current_ratio=1.25)
    cs = solvency_score(f)
    text = solvency_explanation(cs)
    assert text.startswith("Solvency ")
    assert "Debt/Equity 50.00" in text
    assert "Current ratio 1.25" in text


def test_solvency_explanation_insufficient_data():
    cs = solvency_score(Fundamentals(symbol="X"))
    assert solvency_explanation(cs) == (
        "Insufficient data to compute a solvency score."
    )


def test_valuation_explanation_reflects_result():
    r = relative_valuation("RELIANCE.NS", "PE", 20.0, [30.0])
    text = valuation_explanation(r)
    assert text.startswith("RELIANCE.NS trades at P/E 20.0")
    assert "undervalued by 33.3%" in text


def test_valuation_explanation_fairly_valued():
    r = relative_valuation("RELIANCE.NS", "PE", 20.0, [20.0])
    text = valuation_explanation(r)
    assert "fairly valued by 0.0%" in text