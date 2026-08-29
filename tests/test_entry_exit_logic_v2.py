from entry_exit_logic_v2 import entry_signal, entry_signal_details, exit_signal


def test_regime_setup_trigger_accepts_clean_trend_pullback():
    prices = [100.0, 100.3, 100.6, 100.8, 101.0, 101.2, 101.4, 101.1, 101.25, 101.5, 101.8, 102.0, 102.1]
    assert entry_signal(prices) == (True, "confirmed")


def test_regime_setup_trigger_rejects_chase_without_pullback():
    prices = [100.0, 100.3, 100.6, 100.9, 101.2, 101.5, 101.8, 102.1, 102.4, 102.7, 103.0, 103.3]
    assert entry_signal(prices)[0] is False


def test_short_uses_mirrored_regime_and_trigger():
    prices = [100.0, 99.7, 99.4, 99.2, 99.0, 98.8, 98.6, 98.9, 98.75, 98.5, 98.2, 98.0, 97.9]
    assert entry_signal(prices, "SHORT")[0] is True


def test_exit_has_hysteresis_against_small_pullback():
    prices = [100.0, 100.4, 100.8, 101.0, 101.2, 101.1, 100.9, 100.8, 100.9, 100.8, 100.7, 100.6]
    assert exit_signal(prices, "LONG") is False


def test_diagnostics_expose_setup_and_regime_components():
    prices = [100.0, 100.2, 100.4, 100.6, 100.8, 100.7, 100.6, 100.75, 100.9, 101.0, 101.1, 101.2]
    _, _, _, diagnostics = entry_signal_details(prices, "LONG")
    assert "trend" in diagnostics
    assert "bounce_checks" in diagnostics
