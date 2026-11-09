# Stale-frame guard tests (2026-11-09 runner outage): yfinance silently
# returned history frames that ended months back for some liquid symbols
# (RELIANCE.NS/TCS.NS cut at 2026-09-08 across three nightly runs), which
# upserted idempotently over stored rows and froze the series with zero
# errors. The guard converts that shape into a retryable MarketDataError.

from datetime import date, timedelta

import pytest

from app.jobs import STALE_FRAME_MAX_AGE_DAYS, _assert_frame_fresh
from app.providers.base import OHLCV
from app.providers.yfinance_provider import MarketDataError


def _bars(days_ago: int, n: int = 2):
    base = date.today() - timedelta(days=days_ago)
    return [
        OHLCV(
            date=base - timedelta(days=i),
            open=1.0, high=1.0, low=1.0, close=1.0, volume=0, source="test",
        )
        for i in range(n)
    ]


def test_fresh_frame_passes():
    _assert_frame_fresh("X.NS", _bars(1))
    _assert_frame_fresh("X.NS", _bars(STALE_FRAME_MAX_AGE_DAYS))


def test_empty_frame_passes_to_caller_skip_path():
    _assert_frame_fresh("X.NS", [])


def test_stale_frame_raises_retryable_error():
    with pytest.raises(MarketDataError, match="stale price frame"):
        _assert_frame_fresh("RELIANCE.NS", _bars(days_ago=60))


def test_error_names_the_last_bar_date():
    bars = _bars(days_ago=60)
    newest = max(b.date for b in bars)
    with pytest.raises(MarketDataError) as exc:
        _assert_frame_fresh("RELIANCE.NS", bars)
    assert str(newest) in str(exc.value)
