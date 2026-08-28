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


def entry_signal_details(prices: list[float]) -> tuple[bool, str, int, dict[str, bool]]:
    """Return the entry decision plus the five-factor confirmation breakdown."""
    if len(prices) < 12:
        return False, "insufficient_history", 0, {}
    price = prices[-1]
    fast = ema(prices[-8:], 5)
    slow = ema(prices[-12:], 10)
    if fast is None or slow is None:
        return False, "insufficient_history", 0, {}

    short_return = prices[-1] / prices[-4] - 1.0
    medium_return = prices[-1] / prices[-10] - 1.0
    recent = [prices[i] / prices[i - 1] - 1.0 for i in range(len(prices) - 3, len(prices))]
    positive_moves = sum(1 for move in recent if move > 0)
    negative_moves = sum(1 for move in recent if move < 0)

    confirmations = {
        "trend": fast >= slow,
        "price_near_fast": price >= fast * 0.999,
        "medium_momentum": medium_return >= 0.0005,
        "short_momentum": short_return >= 0.0005,
        "positive_microstructure": positive_moves >= 2,
    }
    score = sum(confirmations.values())

    if fast < slow * 0.9985 or price < slow * 0.9970:
        return False, "trend_not_confirmed", score, confirmations
    if price > fast * 1.0085:
        return False, "overextended", score, confirmations
    if negative_moves == 3:
        return False, "short_term_reversal", score, confirmations
    if score < 4:
        return False, "momentum_not_confirmed", score, confirmations
    return True, "confirmed", score, confirmations


def entry_signal(prices: list[float]) -> tuple[bool, str]:
    """Use multi-factor confirmation while preserving anti-chasing protection."""
    ready, reason, _score, _confirmations = entry_signal_details(prices)
    return ready, reason


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
