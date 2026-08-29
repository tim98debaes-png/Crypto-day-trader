"""Regime -> setup -> trigger entry architecture for short-horizon crypto paper research."""
from __future__ import annotations


def ema(values: list[float], period: int) -> float | None:
    if not values:
        return None
    alpha = 2.0 / (period + 1.0)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def _returns(values: list[float]) -> list[float]:
    return [values[i] / values[i - 1] - 1.0 for i in range(1, len(values)) if values[i - 1] > 0]


def entry_signal_details(prices: list[float], direction: str = "LONG"):
    if len(prices) < 12:
        return False, "insufficient_history", 0, {}
    direction = direction.upper()
    if direction not in {"LONG", "SHORT"}:
        return False, "invalid_direction", 0, {}
    price = prices[-1]
    fast = ema(prices[-8:], 5)
    medium = ema(prices[-21:], 13) if len(prices) >= 21 else ema(prices[-12:], 8)
    slow = ema(prices[-34:], 21) if len(prices) >= 34 else ema(prices[-12:], 10)
    assert fast is not None and medium is not None and slow is not None
    short_return = price / prices[-4] - 1.0
    medium_return = price / prices[-10] - 1.0
    long_return = price / prices[-min(25, len(prices))] - 1.0
    recent = _returns(prices[-4:])
    positive = sum(move > 0 for move in recent)
    negative = sum(move < 0 for move in recent)
    pullback = prices[-8:-3]
    trigger = prices[-3:]
    pullback_return = pullback[-1] / pullback[0] - 1.0

    if direction == "LONG":
        regime = fast > medium > slow and long_return > 0.0015
        touched = min(pullback) <= fast * 1.002
        actual_pullback = pullback_return <= -0.0010
        reclaimed = price > fast * 1.001
        followthrough = trigger[-1] > trigger[0] * 1.0006 and trigger[-1] > trigger[-2]
        structure = trigger[-1] > min(pullback) * 1.001
        medium_ok = medium_return > 0.0010
        short_ok = short_return > 0.0003
        micro_ok = positive >= 2
        if not regime:
            return False, "trend_not_confirmed", 0, {"trend": False, "pullback_return": pullback_return}
        if price > fast * 1.0065:
            return False, "overextended", 0, {"trend": True, "pullback_return": pullback_return}
        if negative == 3:
            return False, "short_term_reversal", 0, {"trend": True, "pullback_return": pullback_return}
    else:
        regime = fast < medium < slow and long_return < -0.0015
        touched = max(pullback) >= fast * 0.998
        actual_pullback = pullback_return >= 0.0010
        reclaimed = price < fast * 0.999
        followthrough = trigger[-1] < trigger[0] * 0.9994 and trigger[-1] < trigger[-2]
        structure = trigger[-1] < max(pullback) * 0.999
        medium_ok = medium_return < -0.0010
        short_ok = short_return < -0.0003
        micro_ok = negative >= 2
        if not regime:
            return False, "trend_not_confirmed", 0, {"trend": False, "pullback_return": pullback_return}
        if price < fast * 0.9935:
            return False, "overextended", 0, {"trend": True, "pullback_return": pullback_return}
        if positive == 3:
            return False, "short_term_reversal", 0, {"trend": True, "pullback_return": pullback_return}

    confirmations = {
        "trend": regime,
        "price_near_fast": abs(price / fast - 1.0) <= 0.0065,
        "medium_momentum": medium_ok,
        "short_momentum": short_ok,
        "positive_microstructure": micro_ok,
        "microstructure": micro_ok,
        "pullback_bounce": touched and actual_pullback and reclaimed and followthrough and structure,
        "bounce_score": int(touched) + int(actual_pullback) + int(reclaimed) + int(followthrough) + int(structure),
        "bounce_checks": {
            "pullback_touch": touched,
            "actual_countertrend_pullback": actual_pullback,
            "ema_reclaim": reclaimed,
            "directional_followthrough": followthrough,
            "pullback_structure": structure,
        },
        "regime_strength": abs(long_return),
        "pullback_return": pullback_return,
    }
    score = sum(bool(confirmations[k]) for k in ("trend", "price_near_fast", "medium_momentum", "short_momentum", "positive_microstructure"))
    if not touched or not actual_pullback:
        return False, "pullback_not_confirmed", score, confirmations
    if not confirmations["pullback_bounce"]:
        return False, "trigger_not_confirmed", score, confirmations
    if score < 5:
        return False, "momentum_not_confirmed", score, confirmations
    return True, "confirmed", score, confirmations


def entry_signal(prices: list[float], direction: str = "LONG"):
    ready, reason, _, _ = entry_signal_details(prices, direction)
    return ready, reason


def exit_signal(prices: list[float], direction: str = "LONG"):
    if len(prices) < 12:
        return False
    direction = direction.upper()
    fast = ema(prices[-8:], 5)
    slow = ema(prices[-21:], 13) if len(prices) >= 21 else ema(prices[-12:], 8)
    if fast is None or slow is None:
        return False
    recent = _returns(prices[-4:])
    negative = sum(move < 0 for move in recent)
    positive = sum(move > 0 for move in recent)
    short_return = prices[-1] / prices[-4] - 1.0
    if direction == "LONG":
        return prices[-1] < fast * 0.998 and fast < slow and negative >= 3 and short_return < -0.0008
    if direction == "SHORT":
        return prices[-1] > fast * 1.002 and fast > slow and positive >= 3 and short_return > 0.0008
    return False
