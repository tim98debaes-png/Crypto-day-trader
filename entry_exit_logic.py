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
    """Use multi-factor confirmation while preserving anti-chasing protection."""
    if len(prices) < 12:
        return False, "insufficient_history"
    price = prices[-1]
    fast = ema(prices[-8:], 5)
    slow = ema(prices[-12:], 10)
    if fast is None or slow is None:
        return False, "insufficient_history"

    short_return = prices[-1] / prices[-4] - 1.0
    medium_return = prices[-1] / prices[-10] - 1.0
    recent = [prices[i] / prices[i - 1] - 1.0 for i in range(len(prices) - 3, len(prices))]
    positive_moves = sum(1 for move in recent if move > 0)
    negative_moves = sum(1 for move in recent if move < 0)

    if fast < slow * 0.9985 or price < slow * 0.9970:
        return False, "trend_not_confirmed"
    if price > fast * 1.0085:
        return False, "overextended"
    if negative_moves == 3:
        return False, "short_term_reversal"

    score = 0
    score += 1 if fast >= slow else 0
    score += 1 if price >= fast * 0.999 else 0
    score += 1 if medium_return >= 0.0005 else 0
    score += 1 if short_return >= 0.0005 else 0
    score += 1 if positive_moves >= 2 else 0
    if score < 4:
        return False, "momentum_not_confirmed"
    return True, "confirmed"


def exit_signal(prices: list[float]) -> bool:
    """Exit on multi-factor deterioration while allowing ordinary pullbacks."""
    if len(prices) < 12:
        return False
    fast = ema(prices[-8:], 5)
    slow = ema(prices[-12:], 10)
    if fast is None or slow is None:
        return False

    recent = [prices[i] / prices[i - 1] - 1.0 for i in range(len(prices) - 3, len(prices))]
    negative_moves = sum(1 for move in recent if move < 0)
    short_return = prices[-1] / prices[-4] - 1.0

    trend_break = prices[-1] < fast * 0.9985 and fast < slow
    sustained_weakness = negative_moves == 3 or (negative_moves >= 2 and short_return < -0.0008)
    return trend_break and sustained_weakness
