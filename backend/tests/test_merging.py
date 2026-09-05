# Phase 6.5 Part F tests — MergingProvider and the pure merge helpers.
# No network: both sides are in-memory fake providers.

import logging
from datetime import date, timedelta

import pytest

from app.providers.base import (
    FinancialPeriodDraft,
    Fundamentals,
    MarketDataError,
    MarketDataProvider,
    OHLCV,
    StockProfile,
)
from app.providers.merging import (
    MergingProvider,
    merge_financial_history,
    merge_fundamentals,
    merge_price_bars,
)


def _bar(day: str, close: float, source: str | None = None) -> OHLCV:
    d = date.fromisoformat(day)
    return OHLCV(date=d, open=close, high=close, low=close, close=close, volume=100,
                 source=source)


class _ScriptedProvider(MarketDataProvider):
    """Fake provider returning canned results; can fail per capability."""

    name = "scripted"

    def __init__(
        self,
        bars: list[OHLCV] | Exception = None,
        profile: StockProfile | Exception | None = None,
        fundamentals: Fundamentals | Exception | None = None,
        history: list[FinancialPeriodDraft] | Exception | None = None,
    ):
        self.bars = bars if bars is not None else []
        self.profile = profile
        self.fundamentals = fundamentals
        self.history = history

    async def get_price_history(self, symbol: str, period: str) -> list[OHLCV]:
        if isinstance(self.bars, Exception):
            raise self.bars
        return self.bars

    async def get_stock_profile(self, symbol: str) -> StockProfile:
        if isinstance(self.profile, Exception):
            raise self.profile
        if self.profile is None:
            raise NotImplementedError
        return self.profile

    async def get_fundamentals(self, symbol: str) -> Fundamentals:
        if isinstance(self.fundamentals, Exception):
            raise self.fundamentals
        if self.fundamentals is None:
            raise NotImplementedError
        return self.fundamentals

    async def get_financial_history(self, symbol: str) -> list[FinancialPeriodDraft]:
        if isinstance(self.history, Exception):
            raise self.history
        if self.history is None:
            raise NotImplementedError
        return self.history


# --- Price merging --------------------------------------------------------------


def test_price_merge_primary_wins_collisions():
    a = [_bar("2026-01-01", 100, "primary"), _bar("2026-01-02", 101, "primary")]
    b = [_bar("2026-01-02", 999, "secondary"), _bar("2026-01-03", 102, "secondary")]
    merged = merge_price_bars(a, b)
    assert [bar.close for bar in merged] == [100, 101, 102]
    assert [bar.date.isoformat() for bar in merged] == [
        "2026-01-01", "2026-01-02", "2026-01-03",
    ]
    # Source attribution survives the merge per bar.
    assert [bar.source for bar in merged] == ["primary", "primary", "secondary"]


def test_price_merge_gap_fill_sorted():
    a = [_bar("2026-01-05", 105, "primary")]
    b = [_bar("2026-01-01", 100, "secondary"), _bar("2026-01-03", 103, "secondary")]
    merged = merge_price_bars(a, b)
    assert [bar.date.isoformat() for bar in merged] == [
        "2026-01-01", "2026-01-03", "2026-01-05",
    ]


async def test_merging_provider_secondary_failure_degrades_to_primary():
    primary = _ScriptedProvider(bars=[_bar("2026-01-01", 100, "yfinance")])
    secondary = _ScriptedProvider(bars=MarketDataError("upstox down"))
    merged = MergingProvider(primary, secondary)
    bars = await merged.get_price_history("RELIANCE.NS", "1y")
    assert len(bars) == 1
    assert bars[0].source == "yfinance"


async def test_merging_provider_both_fail_raises():
    primary = _ScriptedProvider(bars=MarketDataError("primary down"))
    secondary = _ScriptedProvider(bars=MarketDataError("secondary down"))
    merged = MergingProvider(primary, secondary)
    with pytest.raises(MarketDataError):
        await merged.get_price_history("RELIANCE.NS", "1y")


async def test_merging_provider_gap_fills_from_secondary():
    primary = _ScriptedProvider(
        bars=[_bar("2026-01-01", 100, "yfinance"), _bar("2026-01-03", 102, "yfinance")]
    )
    secondary = _ScriptedProvider(
        bars=[_bar("2026-01-01", 100, "upstox"), _bar("2026-01-02", 101, "upstox")]
    )
    merged = MergingProvider(primary, secondary)
    bars = await merged.get_price_history("RELIANCE.NS", "1y")
    assert [bar.date.day for bar in bars] == [1, 2, 3]
    assert bars[1].source == "upstox"


# --- Fundamentals coalesce --------------------------------------------------------


def test_fundamentals_coalesce_prefers_non_null():
    p = Fundamentals(symbol="X", market_cap=100.0, trailing_pe=None)
    s = Fundamentals(symbol="X", market_cap=999.0, trailing_pe=20.0)
    merged = merge_fundamentals(p, s, "X")
    assert merged.market_cap == 100.0      # primary kept
    assert merged.trailing_pe == 20.0      # secondary filled a null


def test_fundamentals_disagreement_keeps_primary_and_logs(caplog):
    p = Fundamentals(symbol="X", trailing_pe=20.0)
    s = Fundamentals(symbol="X", trailing_pe=60.0)  # 200% apart: material
    with caplog.at_level(logging.INFO):
        merged = merge_fundamentals(p, s, "X")
    assert merged.trailing_pe == 20.0
    assert any(
        "fundamentals disagreement" in rec.message and "trailing_pe" in rec.message
        for rec in caplog.records
    )


def test_fundamentals_small_differences_not_flagged(caplog):
    p = Fundamentals(symbol="X", trailing_pe=20.0)
    s = Fundamentals(symbol="X", trailing_pe=20.5)  # 2.5%: within tolerance
    with caplog.at_level(logging.INFO):
        merged = merge_fundamentals(p, s, "X")
    assert merged.trailing_pe == 20.0
    assert not any("fundamentals disagreement" in rec.message for rec in caplog.records)


async def test_merging_provider_fundamentals_merge():
    primary = _ScriptedProvider(
        fundamentals=Fundamentals(symbol="RELIANCE.NS", market_cap=1.0, return_on_equity=None)
    )
    secondary = _ScriptedProvider(
        fundamentals=Fundamentals(symbol="RELIANCE.NS", market_cap=2.0, return_on_equity=0.09)
    )
    merged = MergingProvider(primary, secondary)
    f = await merged.get_fundamentals("RELIANCE.NS")
    assert f.market_cap == 1.0
    assert f.return_on_equity == 0.09


# --- Financial history coalesce ---------------------------------------------------


def _period(day: str, **fields) -> FinancialPeriodDraft:
    return FinancialPeriodDraft(
        period_end=date.fromisoformat(day), period_type="annual", **fields
    )


def test_financial_history_fills_missing_fields_and_periods():
    p = [_period("2026-03-31", revenue=100.0, net_income=10.0)]
    s = [_period("2026-03-31", revenue=100.0, net_income=10.0, eps=5.0),
         _period("2025-03-31", revenue=90.0)]
    merged = merge_financial_history(p, s, "X")
    assert len(merged) == 2
    by_end = {d.period_end: d for d in merged}
    assert by_end[date(2026, 3, 31)].eps == 5.0        # secondary filled eps
    assert by_end[date(2026, 3, 31)].revenue == 100.0  # primary kept
    assert by_end[date(2025, 3, 31)].revenue == 90.0   # secondary-only period


def test_financial_history_disagreement_keeps_primary(caplog):
    p = [_period("2026-03-31", revenue=100.0)]
    s = [_period("2026-03-31", revenue=300.0)]
    with caplog.at_level(logging.INFO):
        merged = merge_financial_history(p, s, "X")
    assert merged[0].revenue == 100.0
    assert any("financial history disagreement" in rec.message for rec in caplog.records)


def test_financial_history_source_attribution():
    p = [_period("2026-03-31", revenue=100.0, net_income=10.0)]
    s = [_period("2026-03-31", revenue=100.0, net_income=10.0, eps=5.0)]
    merged = merge_financial_history(p, s, "X")
    assert merged[0].source == "merged"  # fields from both providers

    only_primary = merge_financial_history(p, [], "X")
    assert only_primary[0].source == "yfinance"

    only_secondary = merge_financial_history([], s, "X")
    assert only_secondary[0].source == "upstox"


async def test_merging_provider_history_secondary_not_implemented():
    primary = _ScriptedProvider(history=[_period("2026-03-31", revenue=100.0)])
    secondary = _ScriptedProvider()  # history -> NotImplementedError
    merged = MergingProvider(primary, secondary)
    periods = await merged.get_financial_history("RELIANCE.NS")
    assert len(periods) == 1
    assert periods[0].source == "yfinance"


async def test_merging_provider_history_secondary_failure_is_not_fatal():
    primary = _ScriptedProvider(history=[_period("2026-03-31", revenue=100.0)])
    secondary = _ScriptedProvider(history=MarketDataError("upstox down"))
    merged = MergingProvider(primary, secondary)
    periods = await merged.get_financial_history("RELIANCE.NS")
    assert len(periods) == 1


# --- Profile coalesce ---------------------------------------------------------------


async def test_merging_provider_profile_fills_missing_fields():
    primary = _ScriptedProvider(profile=StockProfile(symbol="RELIANCE.NS", name="Reliance Industries", sector=None, industry=None))
    secondary = _ScriptedProvider(profile=StockProfile(symbol="RELIANCE.NS", name=None, sector="Energy", industry="Refineries"))
    merged = MergingProvider(primary, secondary)
    profile = await merged.get_stock_profile("RELIANCE.NS")
    assert profile.name == "Reliance Industries"
    assert profile.sector == "Energy"
    assert profile.industry == "Refineries"
