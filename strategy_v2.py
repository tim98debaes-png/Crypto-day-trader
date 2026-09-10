"""Independent Strategy V2: multi-timeframe trend pullback continuation."""
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
    for candle in candles:
        value = _field(candle, "close")
        if value is None or value <= 0:
            return []
        out.append(value)
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
    previous_close = _field(candles[-period - 1], "close")
    if previous_close is None:
        return None
    true_ranges: list[float] = []
    for candle in candles[-period:]:
        high = _field(candle, "high")
        low = _field(candle, "low")
        close = _field(candle, "close")
        if high is None or low is None or close is None or high < low:
            return None
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
        previous_close = close
    return sum(true_ranges) / len(true_ranges)


def _slope(values: Sequence[float], lookback: int) -> float | None:
    if len(values) < lookback + 1:
        return None
    return values[-1] / values[-1 - lookback] - 1.0


def _relative_volume(candles: Sequence[Mapping[str, object]], lookback: int = 20) -> float | None:
    if len(candles) < lookback + 1:
        return None
    current = _field(candles[-1], "volume")
    history = [_field(candle, "volume") for candle in candles[-lookback - 1:-1]]
    if current is None or current < 0 or any(value is None or value < 0 for value in history):
        return None
    average = sum(value for value in history if value is not None) / len(history)
    return current / average if average > 0 else None


def _structure(candles: Sequence[Mapping[str, object]], direction: str) -> tuple[bool, bool]:
    if len(candles) < 5:
        return False, False
    highs = [_field(candle, "high") for candle in candles[-5:]]
    lows = [_field(candle, "low") for candle in candles[-5:]]
    if any(value is None for value in highs + lows):
        return False, False
    h = [float(value) for value in highs if value is not None]
    l = [float(value) for value in lows if value is not None]
    if direction == "LONG":
        return h[-1] > h[-2] and l[-1] > l[-2], h[-1] > h[0] and l[-1] > l[0]
    return h[-1] < h[-2] and l[-1] < l[-2], h[-1] < h[0] and l[-1] < l[0]


def _pullback_trigger(candles: Sequence[Mapping[str, object]], direction: str, atr: float, ema_fast: float) -> tuple[bool, float]:
    if len(candles) < 5 or atr <= 0:
        return False, 0.0
    current, previous = candles[-1], candles[-2]
    close = _field(current, "close")
    high = _field(current, "high")
    low = _field(current, "low")
    open_ = _field(current, "open")
    previous_close = _field(previous, "close")
    previous_low = _field(previous, "low")
    previous_high = _field(previous, "high")
    lows = [_field(candle, "low") for candle in candles[-5:-1]]
    highs = [_field(candle, "high") for candle in candles[-5:-1]]
    if None in (close, high, low, open_, previous_close, previous_low, previous_high) or any(value is None for value in lows + highs):
        return False, 0.0
    assert close is not None and high is not None and low is not None and open_ is not None
    assert previous_close is not None and previous_low is not None and previous_high is not None
    body = abs(close - open_)
    if direction == "LONG":
        pullback = min(value for value in lows if value is not None)
        reclaimed = close > ema_fast and previous_close <= ema_fast
        impulse = close > previous_high and body / atr >= 0.30 and close > open_
        depth = max(0.0, (ema_fast - pullback) / atr)
    else:
        pullback = max(value for value in highs if value is not None)
        reclaimed = close < ema_fast and previous_close >= ema_fast
        impulse = close < previous_low and body / atr >= 0.30 and close < open_
        depth = max(0.0, (pullback - ema_fast) / atr)
    return reclaimed and impulse and 0.15 <= depth <= 1.5, depth


def generate_signal(candles_5m: Sequence[Mapping[str, object]], candles_15m: Sequence[Mapping[str, object]], candles_1h: Sequence[Mapping[str, object]], btc_1h: Sequence[Mapping[str, object]] | None = None) -> StrategyV2Signal | None:
    if min(len(candles_5m), len(candles_15m), len(candles_1h)) < 50:
        return None
    c5, c15, c1 = _closes(candles_5m), _closes(candles_15m), _closes(candles_1h)
    if not c5 or not c15 or not c1:
        return None
    e1_fast, e1_slow = _ema(c1, 20), _ema(c1, 50)
    e15_fast, e15_slow = _ema(c15, 20), _ema(c15, 50)
    e5_fast, atr5, rv5 = _ema(c5, 20), _atr(candles_5m), _relative_volume(candles_5m)
    if None in (e1_fast, e1_slow, e15_fast, e15_slow, e5_fast, atr5, rv5):
        return None
    assert e1_fast is not None and e1_slow is not None and e15_fast is not None and e15_slow is not None and e5_fast is not None and atr5 is not None and rv5 is not None
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
