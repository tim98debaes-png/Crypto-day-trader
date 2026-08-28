"""Deterministic research-stage entry/exit logic for the live paper strategy."""
from __future__ import annotations


def ema(values: list[float], period: int) -> float | None:
    if not values:
        return None
    alpha = 2.0 / (period + 1.0)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def entry_signal(prices: list[float]) -> tuple[bool, str]:
    """Require trend confirmation while avoiding late momentum chasing."""
    if len(prices) < 12:
        return False, "insufficient_history"
    price = prices[-1]
    fast = ema(prices[-8:], 5)
    slow = ema(prices[-12:], 10)
    if fast is None or slow is None:
        return False, "insufficient_history"
    short_return = prices[-1] / prices[-4] - 1.0
    medium_return = prices[-1] / prices[-10] - 1.0
    last_moves = [prices[i] / prices[i - 1] - 1.0 for i in range(len(prices) - 3, len(prices))]
    if fast <= slow or price < fast:
        return False, "trend_not_confirmed"
    if medium_return < 0.0020 or short_return < -0.0005:
        return False, "momentum_not_confirmed"
    if price > fast * 1.006:
        return False, "overextended"
    if sum(1 for move in last_moves if move < 0) >= 2:
        return False, "short_term_reversal"
    return True, "confirmed"


def exit_signal(prices: list[float]) -> bool:
    """Exit a long only after a confirmed short-term trend reversal."""
    if len(prices) < 12:
        return False
    fast = ema(prices[-8:], 5)
    slow = ema(prices[-12:], 10)
    if fast is None or slow is None:
        return False
    recent_moves = [prices[i] / prices[i - 1] - 1.0 for i in range(len(prices) - 3, len(prices))]
    return all(move < 0 for move in recent_moves) and prices[-1] < fast and fast < slow
