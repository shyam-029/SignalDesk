# Stale-frame guard tests (2026-11-09 runner outage): yfinance silently
# returned history frames that ended months back for some liquid symbols
# (RELIANCE.NS/TCS.NS cut at 2026-09-08 across three nightly runs), which
# upserted idempotently over stored rows and froze the series with zero
# errors. The guard converts that shape into a retryable MarketDataError.
#
# Alias-fallback tests (2026-11-10): renamed catalog symbols (TATAMOTORS ->
# TMPV post-demerger) hit a dead Yahoo ticker forever because the rename
# map was only applied by the Upstox provider. The fetch path now falls
# back to the aliased master symbol.

from datetime import date, timedelta

import pytest

from app.jobs import (
    STALE_FRAME_MAX_AGE_DAYS,
    _alias_fetch_symbol,
    _assert_frame_fresh,
    _fetch_bars_with_alias,
)
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


class _StubProvider:
    """Minimal MarketDataProvider stand-in: scripted per-symbol results."""

    def __init__(self, scripted: dict[str, object]):
        self.scripted = scripted
        self.calls: list[str] = []

    async def get_price_history(self, symbol: str, period: str):
        self.calls.append(symbol)
        result = self.scripted[symbol]
        if isinstance(result, Exception):
            raise result
        return result


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


def test_alias_target_resolves_rename_and_suffix():
    assert _alias_fetch_symbol("TATAMOTORS.NS") == "TMPV.NS"
    assert _alias_fetch_symbol("TATAMOTORS") == "TMPV"
    assert _alias_fetch_symbol("RELIANCE.NS") is None


async def test_fresh_primary_is_used_and_alias_never_called():
    p = _StubProvider({"RELIANCE.NS": _bars(1)})
    bars = await _fetch_bars_with_alias(p, "RELIANCE.NS")
    assert len(bars) == 2
    assert p.calls == ["RELIANCE.NS"]


async def test_empty_primary_with_no_alias_returns_empty():
    p = _StubProvider({"XYZ.NS": []})
    assert await _fetch_bars_with_alias(p, "XYZ.NS") == []
    assert p.calls == ["XYZ.NS"]


async def test_empty_primary_falls_back_to_renamed_symbol():
    p = _StubProvider({"TATAMOTORS.NS": [], "TMPV.NS": _bars(1)})
    bars = await _fetch_bars_with_alias(p, "TATAMOTORS.NS")
    assert len(bars) == 2
    assert p.calls == ["TATAMOTORS.NS", "TMPV.NS"]


async def test_stale_primary_falls_back_to_renamed_symbol():
    p = _StubProvider({"TATAMOTORS.NS": _bars(days_ago=60), "TMPV.NS": _bars(1)})
    bars = await _fetch_bars_with_alias(p, "TATAMOTORS.NS")
    assert len(bars) == 2
    assert set(p.calls) == {"TATAMOTORS.NS", "TMPV.NS"}
    assert p.calls[-1] == "TMPV.NS"


async def test_stale_primary_without_alias_raises():
    p = _StubProvider({"RELIANCE.NS": _bars(days_ago=60)})
    with pytest.raises(MarketDataError, match="stale price frame"):
        await _fetch_bars_with_alias(p, "RELIANCE.NS")
    # No alias: every attempt stayed on the catalog symbol.
    assert set(p.calls) == {"RELIANCE.NS"}


async def test_stale_alias_result_raises():
    p = _StubProvider(
        {"TATAMOTORS.NS": [], "TMPV.NS": _bars(days_ago=60)}
    )
    with pytest.raises(MarketDataError, match="stale price frame"):
        await _fetch_bars_with_alias(p, "TATAMOTORS.NS")
