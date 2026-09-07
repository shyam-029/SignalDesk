# Phase 7 tests — the freshness classifier (app/services/freshness.py).
#
# Pure unit tests: no DB, no network. Boundaries are tested explicitly.

from datetime import datetime, timedelta, timezone, date

from app.services import freshness


NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def test_missing_timestamp_is_unavailable():
    assert freshness.classify(None, freshness.PRICE_TTL, NOW) == "unavailable"


def test_recent_timestamp_is_current():
    ts = NOW - timedelta(hours=6)
    assert freshness.classify(ts, freshness.PRICE_TTL, NOW) == "current"


def test_old_timestamp_is_stale():
    ts = NOW - timedelta(days=10)
    assert freshness.classify(ts, freshness.PRICE_TTL, NOW) == "stale"


def test_boundary_is_stale_just_past_ttl():
    inside = NOW - freshness.PRICE_TTL + timedelta(seconds=1)
    outside = NOW - freshness.PRICE_TTL - timedelta(seconds=1)
    assert freshness.classify(inside, freshness.PRICE_TTL, NOW) == "current"
    assert freshness.classify(outside, freshness.PRICE_TTL, NOW) == "stale"


def test_accepts_plain_dates():
    # A price bar from "yesterday" is current; last week is stale.
    assert freshness.classify(date(2026, 9, 6), freshness.PRICE_TTL, NOW) == "current"
    assert freshness.classify(date(2026, 8, 1), freshness.PRICE_TTL, NOW) == "stale"


def test_naive_datetime_treated_as_utc():
    naive = datetime(2026, 9, 7, 11, 0)  # no tzinfo
    assert freshness.classify(naive, freshness.PRICE_TTL, NOW) == "current"


def test_is_stale_three_valued():
    assert freshness.is_stale(None, freshness.PRICE_TTL, NOW) is None
    assert freshness.is_stale(NOW, freshness.PRICE_TTL, NOW) is False
    assert freshness.is_stale(NOW - timedelta(days=9), freshness.PRICE_TTL, NOW) is True


def test_domain_ttls_are_sane():
    assert freshness.NEWS_TTL == timedelta(days=60)  # matches the news window
    assert freshness.FUNDAMENTALS_TTL > freshness.PRICE_TTL
