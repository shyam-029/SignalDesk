# Unit tests for the relative-valuation service (PLANNING §8). Pure functions.

import pytest

from app.providers.base import Fundamentals
from app.services.valuation import (
    InsufficientDataError,
    NoPeersError,
    compute_multiple,
    relative_valuation,
)


# --- compute_multiple -------------------------------------------------------


def test_compute_pe_from_trailing_pe():
    f = Fundamentals(symbol="X", trailing_pe=28.4)
    assert compute_multiple("PE", f) == 28.4


def test_compute_ev_ebitda():
    f = Fundamentals(symbol="X", enterprise_value=1000.0, ebitda=100.0)
    assert compute_multiple("EV_EBITDA", f) == 10.0


def test_compute_ev_ebitda_zero_ebitda_is_none():
    f = Fundamentals(symbol="X", enterprise_value=1000.0, ebitda=0.0)
    assert compute_multiple("EV_EBITDA", f) is None


def test_compute_ev_ebitda_negative_ebitda_is_none():
    f = Fundamentals(symbol="X", enterprise_value=1000.0, ebitda=-50.0)
    assert compute_multiple("EV_EBITDA", f) is None


def test_compute_ev_ebitda_missing_is_none():
    f = Fundamentals(symbol="X", enterprise_value=1000.0)
    assert compute_multiple("EV_EBITDA", f) is None


def test_compute_pb_ps_direct():
    f = Fundamentals(symbol="X", price_to_book=1.5, price_to_sales=2.0)
    assert compute_multiple("PB", f) == 1.5
    assert compute_multiple("PS", f) == 2.0


# --- relative_valuation -----------------------------------------------------


def test_undervalued_status():
    r = relative_valuation("X", "PE", 20.0, [30.0, 30.0, 30.0])
    assert r.status == "undervalued"
    assert r.margin_pct == pytest.approx(-33.33, abs=0.01)


def test_fairly_valued_within_band():
    # median 20, current 20 -> margin 0 -> fairly_valued
    r = relative_valuation("X", "PE", 20.0, [20.0])
    assert r.status == "fairly_valued"
    assert r.margin_pct == 0.0


def test_fairly_valued_at_exact_minus_5():
    # median 100, current 95 -> -5 exactly -> fairly_valued
    r = relative_valuation("X", "PE", 95.0, [100.0])
    assert r.status == "fairly_valued"


def test_overvalued_above_5():
    r = relative_valuation("X", "PE", 110.0, [100.0])
    assert r.status == "overvalued"
    assert r.margin_pct == pytest.approx(10.0)


def test_median_even_count():
    r = relative_valuation("X", "PE", 20.0, [10.0, 20.0, 30.0, 40.0])
    # median = (20+30)/2 = 25
    assert r.peer_median == 25.0


def test_median_odd_count():
    r = relative_valuation("X", "PE", 20.0, [10.0, 20.0, 30.0])
    assert r.peer_median == 20.0


def test_peers_filter_negative_and_none():
    r = relative_valuation("X", "PE", 20.0, [None, -5.0, 0.0, 30.0, 40.0])
    # valid: 30, 40 -> median 35
    assert r.peer_median == 35.0
    assert r.peer_count == 2


def test_empty_peers_raises():
    with pytest.raises(NoPeersError):
        relative_valuation("X", "PE", 20.0, [None, -1.0, 0.0])


def test_invalid_current_raises():
    with pytest.raises(InsufficientDataError):
        relative_valuation("X", "PE", None, [30.0])


def test_invalid_current_zero_raises():
    with pytest.raises(InsufficientDataError):
        relative_valuation("X", "PE", 0.0, [30.0])


def test_target_excluded_defensively():
    # If the target's own value sneaks into peers, it's still fine — median is
    # over peers; here just verify peers sontaining negatives still work.
    r = relative_valuation("X", "PE", 20.0, [20.0, 30.0])
    assert r.status == "undervalued"