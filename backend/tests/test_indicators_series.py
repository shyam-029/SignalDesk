# Phase 6.5 Part E tests — indicator series must equal the scalar functions.

import random

from app.services import indicators


def _sample_closes(n: int, seed: int = 42) -> list[float]:
    rng = random.Random(seed)
    closes = [100.0]
    for _ in range(n - 1):
        closes.append(max(1.0, closes[-1] * (1 + rng.uniform(-0.02, 0.02))))
    return closes


def test_sma_series_matches_scalar():
    closes = _sample_closes(60)
    series = indicators.sma_series(closes, 20)
    assert len(series) == len(closes)
    assert series[-1] == indicators.sma(closes, 20)
    assert all(v is None for v in series[:19])
    assert series[19] is not None


def test_sma_series_short_input_all_none():
    assert indicators.sma_series([1.0, 2.0], 20) == [None, None]


def test_ema_series_matches_scalar():
    closes = _sample_closes(60)
    series = indicators.ema_series(closes, 12)
    assert series[-1] == indicators.ema(closes, 12)
    assert all(v is None for v in series[:11])
    assert series[11] is not None


def test_rsi_series_matches_scalar():
    closes = _sample_closes(80, seed=7)
    series = indicators.rsi_series(closes, 14)
    assert series[-1] == indicators.rsi(closes, 14)
    assert all(v is None for v in series[:14])
    assert series[14] is not None


def test_rsi_series_short_input_all_none():
    closes = _sample_closes(10)
    assert all(v is None for v in indicators.rsi_series(closes, 14))


def test_macd_series_matches_scalar():
    closes = _sample_closes(80, seed=11)
    series = indicators.macd_series(closes)
    scalar = indicators.macd(closes)
    assert series["macd"][-1] == scalar["macd"]
    assert series["signal"][-1] == scalar["signal"]
    assert series["histogram"][-1] == scalar["histogram"]
    # Before the warm-up windows there are no values at all.
    assert all(v is None for v in series["macd"][:25])
    assert series["macd"][25] is not None


def test_macd_series_short_input_all_none():
    series = indicators.macd_series(_sample_closes(20))
    assert all(v is None for v in series["macd"])
    assert all(v is None for v in series["signal"])
    assert all(v is None for v in series["histogram"])


def test_sma_series_values_are_window_means():
    closes = list(range(1, 31))
    series = indicators.sma_series(closes, 20)
    assert series[19] == sum(range(1, 21)) / 20
    assert series[20] == sum(range(2, 22)) / 20
