from entry_exit_logic import exit_signal


def test_signal_exit_requires_stronger_long_displacement():
    prices = [
        100.66252850932693, 100.72904427064097, 100.94021590135179,
        100.9873944686214, 99.72395673635997, 100.88577994938484,
        100.62934882885759, 100.95371071044305, 99.60160752924202,
        100.45505633055667, 100.2944404928002, 100.00013366014146,
    ]
    # This fixture is a reversal, but the final price is only about 0.193%
    # below the fast EMA. The experiment should therefore reject the SIGNAL
    # exit; the previous 0.15% threshold would have accepted it.
    assert exit_signal(prices, "LONG") is False
