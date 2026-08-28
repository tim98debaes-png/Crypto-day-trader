from entry_exit_logic import entry_signal_details


def test_entry_logic_supports_both_directions_without_invalid_direction():
    prices = [100.0,100.2,100.1,100.3,100.0,99.9,100.1,100.4,100.6,100.7,100.8,101.0,101.2]
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
