"""Research-stage bidirectional entry/exit logic with confirmed pullback bounce."""
from __future__ import annotations


def ema(values: list[float], period: int) -> float | None:
    if not values:
        return None
    alpha = 2.0 / (period + 1.0)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def _entry_metrics(prices: list[float], direction: str):
    price = prices[-1]
    fast = ema(prices[-8:], 5)
    slow = ema(prices[-12:], 10)
    assert fast is not None and slow is not None
    short = price / prices[-4] - 1.0
    medium = price / prices[-10] - 1.0
    recent = [prices[i] / prices[i - 1] - 1.0 for i in range(len(prices) - 3, len(prices))]
    positive = sum(move > 0 for move in recent)
    negative = sum(move < 0 for move in recent)
    pullback_window = prices[-7:-3]
    confirmation_window = prices[-3:]
    if direction == "LONG":
        touched = min(pullback_window) <= fast * 1.0015
        # Reclaim must be decisive enough to distinguish a genuine bounce
        # from merely touching/crossing the fast EMA.
        reclaimed = price > fast * 1.0015
        bounce = confirmation_window[-1] > confirmation_window[0] * 1.0004
        higher_low = confirmation_window[-1] > min(pullback_window) * 1.0005
        confirmed_bounce = touched and reclaimed and bounce and higher_low
    else:
        touched = max(pullback_window) >= fast * 0.9985
        reclaimed = price < fast * 0.9985
        bounce = confirmation_window[-1] < confirmation_window[0] * 0.9996
        lower_high = confirmation_window[-1] < max(pullback_window) * 0.9995
        confirmed_bounce = touched and reclaimed and bounce and lower_high
    return fast, slow, short, medium, positive, negative, confirmed_bounce, touched


def entry_signal_details(prices: list[float], direction: str = "LONG"):
    if len(prices) < 12:
        return False, "insufficient_history", 0, {}
    direction = direction.upper()
    if direction not in {"LONG", "SHORT"}:
        return False, "invalid_direction", 0, {}
    price = prices[-1]
    fast, slow, short, medium, positive, negative, confirmed_bounce, touched = _entry_metrics(prices, direction)

    # Keep the established five-factor score stable. Pullback/bounce is a
    # separate hard gate and therefore must not inflate the score to 6/6.
    confirmations = {
        "trend": fast >= slow if direction == "LONG" else fast <= slow,
        "price_near_fast": abs(price / fast - 1.0) <= 0.0065,
        "medium_momentum": medium >= 0.0005 if direction == "LONG" else medium <= -0.0005,
        "short_momentum": short >= 0.0005 if direction == "LONG" else short <= -0.0005,
        "positive_microstructure": positive >= 2 if direction == "LONG" else negative >= 2,
    }
    score = sum(confirmations.values())
    if direction == "LONG":
        if fast < slow * 0.9985 or price < slow * 0.997:
            return False, "trend_not_confirmed", score, confirmations
        if price > fast * 1.0065:
            return False, "overextended", score, confirmations
        if negative == 3:
            return False, "short_term_reversal", score, confirmations
    else:
        if fast > slow * 1.0015 or price > slow * 1.003:
            return False, "trend_not_confirmed", score, confirmations
        if price < fast * 0.9935:
            return False, "overextended", score, confirmations
        if positive == 3:
            return False, "short_term_reversal", score, confirmations
    if not touched:
        return False, "pullback_not_confirmed", score, confirmations
    if not confirmed_bounce:
        return False, "bounce_not_confirmed", score, confirmations
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
    slow = ema(prices[-12:], 10)
    if fast is None or slow is None:
        return False
    recent = [prices[i] / prices[i - 1] - 1.0 for i in range(len(prices) - 3, len(prices))]
    negative = sum(move < 0 for move in recent)
    positive = sum(move > 0 for move in recent)
    short = prices[-1] / prices[-4] - 1.0
    if direction == "LONG":
        return prices[-1] < fast * 0.9985 and fast < slow and (negative == 3 or (negative >= 2 and short < -0.0008))
    if direction == "SHORT":
        return prices[-1] > fast * 1.0015 and fast > slow and (positive == 3 or (positive >= 2 and short > 0.0008))
    return False
