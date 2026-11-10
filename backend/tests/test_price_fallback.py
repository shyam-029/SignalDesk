# Upstox as a price fallback behind Yahoo (providers/fallback.py).

from datetime import date, timedelta

import pytest

from app.providers import factory
from app.providers.base import MarketDataError, OHLCV
from app.providers.fallback import PriceFallbackProvider

TODAY = date(2026, 11, 10)


def _bars(last: date, n: int = 3, source: str = "yahoo") -> list[OHLCV]:
    return [
        OHLCV(date=last - timedelta(days=n - 1 - i), open=1, high=1, low=1,
              close=100 + i, volume=10, source=source)
        for i in range(n)
    ]


class _Fake:
    def __init__(self, bars=None, error: bool = False):
        self.bars = bars or []
        self.error = error
        self.calls = 0

    async def get_price_history(self, symbol, period):
        self.calls += 1
        if self.error:
            raise MarketDataError("boom")
        return list(self.bars)

    async def get_fundamentals(self, symbol):
        self.calls += 1
        return "yahoo-fundamentals"


async def test_healthy_yahoo_never_calls_upstox():
    yahoo, upstox = _Fake(_bars(TODAY)), _Fake(_bars(TODAY, source="upstox"))
    p = PriceFallbackProvider(yahoo, upstox, today=TODAY)
    bars = await p.get_price_history("RELIANCE.NS", "2y")
    assert [b.source for b in bars] == ["yahoo"] * 3
    assert upstox.calls == 0 and p.fallbacks == {}


@pytest.mark.parametrize(
    "yahoo, reason",
    [
        (_Fake(error=True), "primary_error"),
        (_Fake([]), "primary_empty"),
        (_Fake(_bars(TODAY - timedelta(days=60))), "primary_stale"),
    ],
)
async def test_unusable_yahoo_falls_back_to_upstox(yahoo, reason):
    upstox = _Fake(_bars(TODAY, n=5, source="upstox"))
    p = PriceFallbackProvider(yahoo, upstox, today=TODAY)
    bars = await p.get_price_history("TCS.NS", "2y")
    assert upstox.calls == 1
    assert p.fallbacks == {reason: 1}
    assert max(b.date for b in bars) == TODAY


async def test_yahoo_wins_every_date_it_has():
    """Stale Yahoo frame: its own dates are kept, Upstox fills only the rest."""
    old = TODAY - timedelta(days=30)
    yahoo = _Fake(_bars(old, n=3))
    upstox = _Fake(_bars(old, n=3, source="upstox") + _bars(TODAY, n=2, source="upstox"))
    p = PriceFallbackProvider(yahoo, upstox, today=TODAY)
    bars = {b.date: b.source for b in await p.get_price_history("X.NS", "2y")}
    assert [bars[d] for d in sorted(bars)] == ["yahoo"] * 3 + ["upstox"] * 2


async def test_both_failing_keeps_the_original_yahoo_error():
    p = PriceFallbackProvider(_Fake(error=True), _Fake(error=True), today=TODAY)
    with pytest.raises(MarketDataError):
        await p.get_price_history("X.NS", "2y")
    assert p.fallback_failures == 1


async def test_stale_yahoo_and_failing_upstox_returns_yahoo_for_the_guard():
    """The caller's stale-frame guard then rejects it, exactly as before."""
    stale = _bars(TODAY - timedelta(days=60))
    p = PriceFallbackProvider(_Fake(stale), _Fake(error=True), today=TODAY)
    assert await p.get_price_history("X.NS", "2y") == stale


async def test_non_price_calls_are_yahoo_only():
    yahoo, upstox = _Fake(), _Fake()
    p = PriceFallbackProvider(yahoo, upstox, today=TODAY)
    assert await p.get_fundamentals("X.NS") == "yahoo-fundamentals"
    assert upstox.calls == 0


def test_factory_uses_fallback_only_with_a_token(monkeypatch):
    monkeypatch.setattr(factory.settings, "upstox_analytics_token", "")
    assert not isinstance(factory.build_default_market_provider(), PriceFallbackProvider)
    monkeypatch.setattr(factory.settings, "upstox_analytics_token", "test-token")
    assert isinstance(factory.build_default_market_provider(), PriceFallbackProvider)
