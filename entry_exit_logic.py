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
    """Use softer confirmation thresholds to avoid starving the strategy of entries."""
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

    # Keep trend confirmation, but allow a small amount of noise around the EMAs.
    if fast < slow * 0.9995 or price < fast * 0.9985:
        return False, "trend_not_confirmed"
    # Require modest positive medium momentum rather than the previous 0.20% hurdle.
    if medium_return < 0.0008 or short_return < -0.0010:
        return False, "momentum_not_confirmed"
    # Keep protection against chasing sharp extensions, but make it less restrictive.
    if price > fast * 1.008:
        return False, "overextended"
    # Permit one down move in the last three observations; reject only a clear reversal.
    if sum(1 for move in last_moves if move < 0) >= 3:
        return False, "short_term_reversal"
    return True, "confirmed"


def exit_signal(prices: list[float]) -> bool:
    """Exit on a confirmed deterioration without reacting to every small pullback."""
    if len(prices) < 12:
        return False
    fast = ema(prices[-8:], 5)
    slow = ema(prices[-12:], 10)
    if fast is None or slow is None:
        return False
    recent_moves = [prices[i] / prices[i - 1] - 1.0 for i in range(len(prices) - 3, len(prices))]
    negative_moves = sum(1 for move in recent_moves if move < 0)
    return negative_moves >= 2 and prices[-1] < fast and fast < slow
