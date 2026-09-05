# Technical indicators — pure functions, no I/O.
#
# Heuristics (product-defined), NOT proven predictive models. Standard
# parameters: SMA 20, EMA 12, RSI 14 (Wilder), MACD 12/26/9.
#
# All functions take a chronological list of close prices and return the LATEST
# value (float) or None when there is insufficient data. They are deliberately
# simple and testable — the Alpha Score combines them with weights.

from statistics import mean


def sma(closes: list[float], period: int = 20) -> float | None:
    """Simple moving average of the last `period` closes."""
    if len(closes) < period:
        return None
    return mean(closes[-period:])


def ema(closes: list[float], period: int = 12) -> float | None:
    """Exponential moving average seeded with the SMA of the first `period`."""
    if len(closes) < period:
        return None
    seed = mean(closes[:period])
    alpha = 2.0 / (period + 1.0)
    value = seed
    for price in closes[period:]:
        value = alpha * price + (1.0 - alpha) * value
    return value


def rsi(closes: list[float], period: int = 14) -> float | None:
    """Relative Strength Index (Wilder smoothing). Needs period+1 closes."""
    if len(closes) < period + 1:
        return None

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    # Seed: simple mean of the first `period` deltas.
    avg_gain = mean(gains[:period])
    avg_loss = mean(losses[:period])

    # Wilder smoothing over the remaining deltas.
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """MACD line, signal, and histogram. Requires slow+signal closes.

    Returns {"macd": float|None, "signal": float|None, "histogram": float|None}.
    """
    ema_fast = _ema_series(closes, fast)
    ema_slow = _ema_series(closes, slow)
    if ema_fast is None or ema_slow is None:
        return {"macd": None, "signal": None, "histogram": None}

    # Align: compute MACD line where both EMA series exist.
    start = slow - fast  # ema_slow has `slow` seeds, ema_fast has `fast`; align from index 0 of slow
    macd_line = [f - s for f, s in zip(ema_fast[start:], ema_slow)]

    if len(macd_line) < signal:
        return {"macd": None, "signal": None, "histogram": None}

    sig = _ema_series(macd_line, signal)
    if sig is None:
        return {"macd": None, "signal": None, "histogram": None}

    current_macd = macd_line[-1]
    current_signal = sig[-1]
    return {
        "macd": current_macd,
        "signal": current_signal,
        "histogram": current_macd - current_signal,
    }


def _ema_series(closes: list[float], period: int) -> list[float] | None:
    """Return the full EMA series (one value per close), or None if short."""
    if len(closes) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    value = mean(closes[:period])
    series = [value]
    for price in closes[period:]:
        value = alpha * price + (1.0 - alpha) * value
        series.append(value)
    return series


def score_technicals(closes: list[float]) -> dict:
    """Combine indicators into a 0-100 technical score (heuristic).

    Weights: trend 50% (price vs SMA20), momentum 30% (MACD histogram),
    reversion 20% (RSI oversold/overbought). Returns per-component scores plus
    the weighted total; any component with insufficient data is omitted and the
    remaining weights are renormalized.
    """
    components: dict[str, float] = {}
    weights: dict[str, float] = {}

    sma20 = sma(closes, 20)
    if sma20 is not None and sma20 != 0:
        close = closes[-1]
        components["trend"] = _clamp(50 + (close / sma20 - 1.0) * 500.0)
        weights["trend"] = 0.5

    hist = macd(closes)["histogram"]
    if hist is not None and closes[-1] != 0:
        components["momentum"] = _clamp(50 + (hist / closes[-1]) * 5000.0)
        weights["momentum"] = 0.3

    rsi_val = rsi(closes, 14)
    if rsi_val is not None:
        components["reversion"] = _clamp(50 + (50.0 - rsi_val) * 0.5)
        weights["reversion"] = 0.2

    if not components:
        return {"components": {}, "score": None}

    total_w = sum(weights.values())
    score = sum(v * weights[k] for k, v in components.items()) / total_w
    return {"components": {k: round(v, 1) for k, v in components.items()},
            "score": round(score)}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """Clamp a value into [low, high]."""
    return max(low, min(high, value))


# --- Series variants (Phase 6.5 Part E: /technicals/series) ----------------
#
# Each series function produces, for every close, the same value the scalar
# function would produce if called on the prefix ending at that close. Tests
# pin this equality (series[-1] == scalar(closes)), so the two stay one math.


def sma_series(closes: list[float], period: int = 20) -> list[float | None]:
    """Rolling SMA; None until `period` closes exist.

    Each value is computed with the same statistics.mean call the scalar
    function uses, so the two agree bit-for-bit.
    """
    out: list[float | None] = [None] * len(closes)
    if len(closes) < period:
        return out
    for i in range(period - 1, len(closes)):
        out[i] = mean(closes[i - period + 1 : i + 1])
    return out


def ema_series(closes: list[float], period: int = 12) -> list[float | None]:
    """EMA series; None until the SMA seed exists, then one value per close.

    Reuses `_ema_series` (the MACD code path) so the seed and smoothing are
    literally the same math.
    """
    out: list[float | None] = [None] * len(closes)
    values = _ema_series(closes, period)
    if values is None:
        return out
    for i, v in enumerate(values):
        out[i + period - 1] = v
    return out


def rsi_series(closes: list[float], period: int = 14) -> list[float | None]:
    """Wilder RSI series; the first value appears at index `period`."""
    out: list[float | None] = [None] * len(closes)
    if len(closes) < period + 1:
        return out

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    def _rsi(avg_gain: float, avg_loss: float) -> float:
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    # Seed: simple mean of the first `period` deltas (index `period` in closes).
    avg_gain = mean(gains[:period])
    avg_loss = mean(losses[:period])
    out[period] = _rsi(avg_gain, avg_loss)

    # Wilder smoothing for every subsequent close (same recursion as rsi()).
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = _rsi(avg_gain, avg_loss)
    return out


def macd_series(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> dict[str, list[float | None]]:
    """MACD line/signal/histogram series aligned to the closes.

    Uses the same alignment as macd(): the MACD line exists where both EMA
    series exist (from index slow-1), the signal is an EMA of that line.
    """
    n = len(closes)
    out: dict[str, list[float | None]] = {
        "macd": [None] * n,
        "signal": [None] * n,
        "histogram": [None] * n,
    }

    ema_fast = _ema_series(closes, fast)
    ema_slow = _ema_series(closes, slow)
    if ema_fast is None or ema_slow is None:
        return out

    macd_line: list[float | None] = [None] * n
    # Same alignment as macd(): pair ema_slow[j] with ema_fast[start + j],
    # where both EMAs are seeded for closes index j + slow - 1.
    start = slow - fast
    for j in range(len(ema_slow)):
        closes_idx = j + slow - 1
        macd_line[closes_idx] = ema_fast[start + j] - ema_slow[j]

    # The signal EMA runs over the contiguous tail of MACD line values.
    tail_start = slow - 1
    valid = [v for v in macd_line[tail_start:] if v is not None]
    sig = _ema_series(valid, signal) if len(valid) >= signal else None
    signal_line: list[float | None] = [None] * n
    if sig is not None:
        for j, v in enumerate(sig):
            signal_line[tail_start + (signal - 1) + j] = v

    for i in range(n):
        m, s = macd_line[i], signal_line[i]
        if m is not None and s is not None:
            out["histogram"][i] = m - s
    out["macd"] = macd_line
    out["signal"] = signal_line
    return out