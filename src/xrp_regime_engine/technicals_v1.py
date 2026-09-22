from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence


@dataclass(frozen=True)
class IndicatorResult:
    value: float | None
    warmup_count: int
    method: str
    quality_flags: tuple[str, ...] = ()


def _finite(values: Sequence[float]) -> tuple[float, ...]:
    data = tuple(float(v) for v in values)
    if any(not isfinite(v) for v in data):
        raise ValueError("indicator input must be finite")
    if any(v <= 0 for v in data):
        raise ValueError("price input must be positive")
    return data


def ema(values: Sequence[float], period: int) -> IndicatorResult:
    data = _finite(values)
    if period < 1:
        raise ValueError("period must be positive")
    if len(data) < period:
        return IndicatorResult(None, len(data), f"EMA{period}:SMA_SEED", ("INSUFFICIENT_WARMUP",))
    seed = sum(data[:period]) / period
    alpha = 2.0 / (period + 1.0)
    current = seed
    for value in data[period:]:
        current = alpha * value + (1.0 - alpha) * current
    return IndicatorResult(current, len(data), f"EMA{period}:SMA_SEED")


def rsi_wilder(values: Sequence[float], period: int = 14) -> IndicatorResult:
    data = _finite(values)
    if period < 1:
        raise ValueError("period must be positive")
    if len(data) < period + 1:
        return IndicatorResult(None, len(data), f"RSI{period}:WILDER", ("INSUFFICIENT_WARMUP",))
    changes = [b - a for a, b in zip(data, data[1:], strict=True)]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:], strict=True):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return IndicatorResult(100.0 if avg_gain > 0 else 50.0, len(data), f"RSI{period}:WILDER")
    rs = avg_gain / avg_loss
    return IndicatorResult(100.0 - (100.0 / (1.0 + rs)), len(data), f"RSI{period}:WILDER")


@dataclass(frozen=True)
class MacdResult:
    macd: float | None
    signal: float | None
    histogram: float | None
    warmup_count: int
    quality_flags: tuple[str, ...] = ()


def macd(values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9) -> MacdResult:
    data = _finite(values)
    if not 0 < fast < slow or signal < 1:
        raise ValueError("MACD periods must satisfy 0 < fast < slow and signal > 0")
    if len(data) < slow + signal - 1:
        return MacdResult(None, None, None, len(data), ("INSUFFICIENT_WARMUP",))

    def series(period: int) -> list[float]:
        seed = sum(data[:period]) / period
        alpha = 2.0 / (period + 1.0)
        out = [seed]
        current = seed
        for value in data[period:]:
            current = alpha * value + (1.0 - alpha) * current
            out.append(current)
        return out

    fast_series = series(fast)
    slow_series = series(slow)
    offset = slow - fast
    macd_series = [
        fast_value - slow_value
        for fast_value, slow_value in zip(fast_series[offset:], slow_series, strict=True)
    ]
    signal_seed = sum(macd_series[:signal]) / signal
    alpha = 2.0 / (signal + 1.0)
    signal_value = signal_seed
    for value in macd_series[signal:]:
        signal_value = alpha * value + (1.0 - alpha) * signal_value
    macd_value = macd_series[-1]
    return MacdResult(macd_value, signal_value, macd_value - signal_value, len(data))
