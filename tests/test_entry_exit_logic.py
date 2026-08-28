from entry_exit_logic import entry_signal, exit_signal


def test_entry_requires_confirmed_trend_and_avoids_chasing():
    rising = [100.0, 100.3, 100.6, 100.8, 101.0, 101.2, 101.4, 101.5, 101.6, 101.8, 102.0, 102.1]
    assert entry_signal(rising) == (True, "confirmed")
    extended = rising[:-1] + [103.2]
    assert entry_signal(extended) == (False, "overextended")


def test_entry_rejects_reversal_and_missing_history():
    assert entry_signal([100.0] * 8)[0] is False
    falling = [100.0, 100.2, 100.4, 100.5, 100.6, 100.5, 100.3, 100.1, 99.9, 99.7, 99.5, 99.3]
    assert entry_signal(falling)[0] is False


def test_entry_uses_multiple_factors_not_one_hard_momentum_threshold():
    balanced = [100.0, 100.08, 100.16, 100.24, 100.20, 100.32, 100.40, 100.48, 100.55, 100.62, 100.70, 100.78]
    assert entry_signal(balanced) == (True, "confirmed")

    weak = [100.0, 100.10, 100.20, 100.30, 100.40, 100.50, 100.60, 100.70, 100.68, 100.67, 100.66, 100.65]
    assert entry_signal(weak)[0] is False


def test_entry_allows_small_short_term_noise_when_trend_remains_aligned():
    noisy = [100.0, 100.12, 100.24, 100.36, 100.31, 100.43, 100.55, 100.50, 100.62, 100.74, 100.70, 100.82]
    assert entry_signal(noisy) == (True, "confirmed")


def test_exit_requires_confirmed_trend_break():
    prices = [100.0, 100.4, 100.8, 101.0, 101.2, 101.1, 100.9, 100.6, 100.3, 100.0, 99.7, 99.4]
    assert exit_signal(prices) is True


def test_exit_does_not_trigger_on_small_pullback():
    prices = [100.0, 100.3, 100.6, 100.9, 101.1, 101.3, 101.5, 101.6, 101.7, 101.6, 101.5, 101.4]
    assert exit_signal(prices) is False
