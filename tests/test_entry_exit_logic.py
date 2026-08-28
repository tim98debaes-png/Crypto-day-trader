import pytest
from entry_exit_logic import entry_signal, exit_signal


def test_entry_requires_confirmed_trend_and_avoids_chasing():
    rising = [100.0, 100.3, 100.6, 100.8, 101.0, 101.2, 101.4, 101.5, 101.6, 101.8, 102.0, 102.1]
    assert entry_signal(rising) == (True, "confirmed")

    extended = rising[:-1] + [103.0]
    assert entry_signal(extended) == (False, "overextended")


def test_entry_rejects_reversal_and_missing_history():
    assert entry_signal([100.0] * 8)[0] is False
    falling = [100.0, 100.2, 100.4, 100.5, 100.6, 100.5, 100.3, 100.1, 99.9, 99.7, 99.5, 99.3]
    assert entry_signal(falling)[0] is False


def test_exit_requires_confirmed_trend_break():
    prices = [100.0, 100.4, 100.8, 101.0, 101.2, 101.1, 100.9, 100.6, 100.3, 100.0, 99.7, 99.4]
    assert exit_signal(prices) is True

    weak_pullback = [100.0, 100.3, 100.6, 100.9, 101.1, 101.3, 101.5, 101.6, 101.7, 101.6, 101.5, 101.4]
    assert exit_signal(weak_pullback) is False
