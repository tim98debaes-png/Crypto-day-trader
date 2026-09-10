"""Independent Strategy V2: multi-timeframe trend pullback continuation.

This module is deliberately independent from the legacy entry_exit_logic module.
It produces a signal from completed OHLCV candles only. Execution, sizing,
fees, slippage, portfolio limits and exits remain outside this module.

Design principles:
- trade continuation after a measurable pullback, not raw indicator crosses;
- require structure agreement on 1h, 15m and 5m;
- use ATR-normalised distances instead of absolute-price thresholds;
- require participation from relative volume on the trigger bar;
- optionally require BTC directional compatibility;
- fail closed on missing/invalid data.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping, Sequence


@dataclass(frozen=True)
class StrategyV2Signal:
    direction: str
    score: int
    reason: str
    entry_price: float
    stop_distance: float
    features: Mapping[str, float | bool]


def _f(value: object) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if isfinite(x) else None


def _field(candle: Mapping[str, object], name: str) -> float | None:
    return _f(candle.get(name))


def _closes(candles: Sequence[Mapping[str, object]]) -> list[float]:
    out: list[float] = []
    for c in candles:
        x = _field(c, "close")
        if x is None or x <= 0:
            return []
        out.append(x)
    return out


def _ema(values: Sequence[float], period: int) -> float | None:
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def _atr(candles: Sequence[Mapping[str, object]], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    trs: list[float] = []
    prev_close = _field(candles[-period - 1], "close")
    if prev_close is None:
        return None
    for c in candles[-period:]:
        high = _field(c, "high")
        low = _field(c, "low")
        close = _field(c, "close")
        if high is None or low is None or close is None or high < low:
            return None
        trs.append(max(high - prev_close, low * 0 + abs(high - prev_close), abs(low - prev_close), high - low))
        prev_close = close
    return sum(trs) / len(trs)


def _slope(values: Sequence[float], lookback: int) -> float | None:
    if len(values) < lookback + 1:
        return None
    return values[-1] / values[-1 - lookback] - 1.0


def _relative_volume(candles: Sequence[Mapping[str, object]], lookback: int = 20) -> float | None:
    if len(candles) < lookback + 1:
        return None
    current = _field(candles[-1], "volume")
    history = [_field(c, "volume") for c in candles[-lookback - 1:-1]]
    if current is None or current < 0 or any(x is None or x < 0 for x in history):
        return None
    avg = sum(x for x in history if x is not None) / len(history)
    return current / avg if avg > 0 else None


def _structure(candles: Sequence[Mapping[str, object]], direction: str) -> tuple[bool, bool]:
    if len(candles) < 4:
        return False, False
    highs = [_field(c, "high") for c in candles[-4:]]
    lows = [_field(c, "low") for c in candles[-4:]]
    if any(x is None for x in highs + lows):
        return False, False
    h = [x for x in highs if x is not None]
    l = [x for x in lows if x is not None]
    if direction == "LONG":
        return h[-1] >= h[-2] and l[-1] >= l[-2], l[-1] > l[0]
    return h[-1] <= h[-2] and l[-1] <= l[-2], h[-1] < h[0]


def _pullback_trigger(candles: Sequence[Mapping[str, object]], direction: str, atr: float, ema_fast: float) -> tuple[bool, float]:
    if len(candles) < 4 or atr <= 0:
        return False, 0.0
    current = candles[-1]
    prev = candles[-2]
    close = _field(current, "close")
    high = _field(current, "high")
    low = _field(current, "low")
    open_ = _field(current, "open")
    prev_close = _field(prev, "close")
    prev_low = _field(prev, "low")
    prev_high = _field(prev, "high")
    lows = [_field(c, "low") for c in candles[-4:-1]]
    highs = [_field(c, "high") for c in candles[-4:-1]]
    if None in (close, high, low, open_, prev_close, prev_low, prev_high) or any(x is None for x in lows + highs):
        return False, 0.0
    assert close is not None and high is not None and low is not None and open_ is not None
    assert prev_close is not None and prev_low is not None and prev_high is not None
    body = abs(close - open_)
    if direction == "LONG":
        pullback = min(x for x in lows if x is not None)
        reclaimed = close > ema_fast and prev_close <= ema_fast * 1.001
        impulse = close > prev_high and body / atr >= 0.25
        depth = max(0.0, (ema_fast - pullback) / atr)
    else:
        pullback = max(x for x in highs if x is not None)
        reclaimed = close < ema_fast and prev_close >= ema_fast * 0.999
        impulse = close < prev_low and body / atr >= 0.25
        depth = max(0.0, (pullback - ema_fast) / atr)
    return reclaimed and impulse and depth <= 1.5, depth


def generate_signal(candles_5m: Sequence[Mapping[str, object]], candles_15m: Sequence[Mapping[str, object]], candles_1h: Sequence[Mapping[str, object]], btc_1h: Sequence[Mapping[str, object]] | None = None) -> StrategyV2Signal | None:
    """Return one signal from completed candles only, otherwise ``None``."""
    if min(len(candles_5m), len(candles_15m), len(candles_1h)) < 30:
        return None
    c5, c15, c1 = _closes(candles_5m), _closes(candles_15m), _closes(candles_1h)
    if not c5 or not c15 or not c1:
        return None
    e1_fast, e1_slow = _ema(c1, 20), _ema(c1, 50)
    e15_fast, e15_slow = _ema(c15, 20), _ema(c15, 50)
    e5_fast, atr5, rv5 = _ema(c5, 20), _atr(candles_5m), _relative_volume(candles_5m)
    if None in (e1_fast, e1_slow, e15_fast, e15_slow, e5_fast, atr5, rv5):
        return None
    assert e1_fast is not None and e1_slow is not None and e15_fast is not None and e15_slow is not None
    assert e5_fast is not None and atr5 is not None and rv5 is not None
    if atr5 <= 0 or rv5 <= 0:
        return None
    slope15, slope1 = _slope(c15, 4), _slope(c1, 4)
    if slope15 is None or slope1 is None:
        return None
    btc_direction = None
    if btc_1h is not None:
        btc = _closes(btc_1h)
        bfast, bslow = _ema(btc, 20), _ema(btc, 50)
        if bfast is None or bslow is None:
            return None
        btc_direction = "LONG" if bfast >= bslow else "SHORT"
    candidates: list[StrategyV2Signal] = []
    for direction in ("LONG", "SHORT"):
        trend = (e1_fast > e1_slow and e15_fast > e15_slow and slope15 > 0 and slope1 > 0) if direction == "LONG" else (e1_fast < e1_slow and e15_fast < e15_slow and slope15 < 0 and slope1 < 0)
        structure, continuation = _structure(c15, direction)
        trigger, pullback_depth = _pullback_trigger(candles_5m, direction, atr5, e5_fast)
        participation = rv5 >= 1.0
        btc_ok = btc_direction is None or btc_direction == direction
        score = sum((trend, structure, continuation, trigger, participation, btc_ok))
        if score < 6:
            continue
        close = c5[-1]
        candidates.append(StrategyV2Signal(direction, score, "v2_trend_pullback_continuation", close, max(atr5 * 1.5, close * 0.003), {"trend": trend, "structure": structure, "continuation": continuation, "trigger": trigger, "participation": participation, "btc_ok": btc_ok, "pullback_depth_atr": pullback_depth, "relative_volume": rv5, "slope_15m": slope15, "slope_1h": slope1}))
    return max(candidates, key=lambda x: x.score) if candidates else None
