# Unit tests for the scoring services (PLANNING §8b + §12: services first).
# Pure functions — no DB, no network.

import pytest

from app.providers.base import Fundamentals
from app.services.scores import (
    _linear,
    profitability_score,
    solvency_score,
)


# --- _linear helper --------------------------------------------------------


@pytest.mark.parametrize(
    "value,floor,ceiling,higher,expected",
    [
        # higher-is-better
        (10, 0, 20, True, 50),  # midpoint
        (0, 0, 20, True, 0),    # floor
        (20, 0, 20, True, 100),  # ceiling
        (-5, 0, 20, True, 0),   # below floor
        (25, 0, 20, True, 100),  # above ceiling
        # lower-is-better (D/E)
        (125, 200, 50, False, 50),   # midpoint
        (50, 200, 50, False, 100),   # ceiling
        (200, 200, 50, False, 0),    # floor
        (-10, 200, 50, False, 100),  # negative D/E -> very solvent
        (300, 200, 50, False, 0),    # above floor
    ],
)
def test_linear_piecewise(value, floor, ceiling, higher, expected):
    assert _linear(value, floor, ceiling, higher) == expected


# --- Profitability ----------------------------------------------------------


def test_profitability_all_missing():
    f = Fundamentals(symbol="X")
    result = profitability_score(f)
    assert result.score is None
    assert result.available is False
    assert result.components == []


def test_profitability_full():
    # ROE 18% (->90), ROA 6% (->50), op 12.5% (->50), net 10% (->50)
    f = Fundamentals(
        symbol="X",
        return_on_equity=0.18,
        return_on_assets=0.06,
        operating_margin=0.125,
        profit_margin=0.10,
    )
    result = profitability_score(f)
    assert result.available is True
    # weighted: .4*90 + .2*50 + .2*50 + .2*50 = 36+10+10+10 = 66
    assert result.score == 66


def test_profitability_renormalizes_missing():
    # Only ROE (40%) and op-margin (20%) present -> weights 2/3, 1/3.
    # ROE 20% -> 100; op 12.5% -> 50; weighted = (2/3)*100 + (1/3)*50 = 83.33
    f = Fundamentals(symbol="X", return_on_equity=0.20, operating_margin=0.125)
    result = profitability_score(f)
    assert result.score == 83
    assert [c.name for c in result.components] == ["ROE", "Operating margin"]


def test_profitability_negative_roe_clamps_to_zero():
    f = Fundamentals(symbol="X", return_on_equity=-0.05)  # only ROE present
    result = profitability_score(f)
    assert result.score == 0
    assert result.components[0].score == 0


# --- Solvency ---------------------------------------------------------------


def test_solvency_full():
    # D/E 50 -> 100; int-cov 3 -> 50; current ratio 1.25 -> 50
    f = Fundamentals(
        symbol="X", debt_to_equity=50.0, interest_coverage=3.0, current_ratio=1.25
    )
    result = solvency_score(f)
    # .5*100 + .3*50 + .2*50 = 50+15+10 = 75
    assert result.score == 75


def test_solvency_negative_de_goes_to_100():
    f = Fundamentals(symbol="X", debt_to_equity=-20.0)
    result = solvency_score(f)
    assert result.score == 100


def test_solvency_renormalizes_missing():
    # Only D/E (50%) and current ratio (20%) -> weights 5/7, 2/7.
    # D/E 125 -> 50; current 2 -> 100; weighted = (5/7)*50 + (2/7)*100 = 64.28 -> 64
    f = Fundamentals(symbol="X", debt_to_equity=125.0, current_ratio=2.0)
    result = solvency_score(f)
    assert result.score == 64