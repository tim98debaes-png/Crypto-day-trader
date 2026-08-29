from entry_exit_logic import entry_signal_details, exit_signal


def test_entry_logic_supports_both_directions():
    prices = [100.0, 100.2, 100.1, 100.3, 100.0, 99.9, 100.1, 100.4, 100.6, 100.8, 101.0, 101.2, 101.5]
    long = entry_signal_details(prices, "LONG")
    short = entry_signal_details(prices, "SHORT")
    assert long[2] >= 0 and short[2] >= 0
    assert long[3] and short[3]


def test_invalid_direction_is_rejected():
    ready, reason, score, confirmations = entry_signal_details([100.0] * 12, "SIDEWAYS")
    assert not ready
    assert reason == "invalid_direction"
    assert score == 0
    assert confirmations == {}


def test_touch_without_reclaim_is_rejected():
    # Touch the pullback area, but fail reclaim/follow-through/structure so
    # the relaxed 3/4 bounce gate is still not satisfied.
    prices = [100.0, 100.3, 100.5, 100.2, 99.7, 99.5, 99.6, 99.7, 99.6, 99.5, 99.6, 99.5]
    ready, reason, _score, confirmations = entry_signal_details(prices, "LONG")
    assert not ready
    assert reason in {"bounce_not_confirmed", "momentum_not_confirmed", "trend_not_confirmed"}
    assert confirmations.get("ema_reclaim", True) is False
    assert confirmations.get("bounce_score", 4) < 3


def test_exit_logic_rejects_invalid_direction():
    prices = [100.0 + i * 0.1 for i in range(12)]
    assert exit_signal(prices, "SIDEWAYS") is False
