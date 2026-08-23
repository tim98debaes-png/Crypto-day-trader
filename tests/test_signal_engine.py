from signal_engine import generate_signal


def candidate():
    return {
        "Status": "TRADE",
        "MC Robustness": 80,
        "MC Profit Probability": 65,
        "OOS Return": 10,
        "signal_threshold": 2,
        "rr": 2,
    }


def test_long_signal_requires_long_score_to_win():
    signal = generate_signal(candidate(), {"long_score": 3, "short_score": 1, "stop_distance": 2})
    assert signal.action == "LONG"
    assert signal.direction == "LONG"


def test_short_signal_requires_short_score_to_win():
    signal = generate_signal(candidate(), {"long_score": 1, "short_score": 3, "stop_distance": 2})
    assert signal.action == "SHORT"
    assert signal.direction == "SHORT"


def test_weak_scores_wait():
    signal = generate_signal(candidate(), {"long_score": 1, "short_score": 1, "stop_distance": 2})
    assert signal.action == "WAIT"


def test_unapproved_candidate_can_never_signal():
    signal = generate_signal({"Status": "WATCH"}, {"long_score": 10, "short_score": 0, "stop_distance": 2})
    assert signal.action == "WAIT"
