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
    """Require aligned trend and momentum while avoiding late/chasing entries."""
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
    positive_moves = sum(1 for move in last_moves if move > 0)

    # Do not buy when the fast trend is materially below the slow trend or
    # when price has already lost the fast trend by more than normal noise.
    if fast < slow * 0.9995 or price < fast * 0.9985:
        return False, "trend_not_confirmed"

    # Require both a modest medium-term edge and a non-negative short-term
    # impulse. This removes many entries that look positive only because of
    # an older move while the current impulse is already fading.
    if medium_return < 0.0012 or short_return < 0.0002 or positive_moves < 2:
        return False, "momentum_not_confirmed"

    # Keep protection against chasing sharp extensions.
    if price > fast * 1.008:
        return False, "overextended"

    # A full 3/3 negative sequence is a clear reversal; one red tick remains
    # acceptable noise and two red ticks are handled by the momentum test.
    if positive_moves == 0:
        return False, "short_term_reversal"
    return True, "confirmed"


def exit_signal(prices: list[float]) -> bool:
    """Exit after a sustained trend break, not a normal two-tick pullback."""
    if len(prices) < 12:
        return False
    fast = ema(prices[-8:], 5)
    slow = ema(prices[-12:], 10)
    if fast is None or slow is None:
        return False

    recent_moves = [prices[i] / prices[i - 1] - 1.0 for i in range(len(prices) - 3, len(prices))]
    negative_moves = sum(1 for move in recent_moves if move < 0)

    # Require a stronger break than a routine pullback: at least two of the
    # last three observations must be negative, price must be below fast EMA
    # by a small buffer, and the fast EMA must be below the slow EMA.
    trend_break = price_below_fast = prices[-1] < fast * 0.9990
    return negative_moves >= 2 and price_below_fast and fast < slow
