import pytest

from v3_exit_engine import adaptive_exit_policy


def test_trend_gives_strong_setup_more_room():
    weak = adaptive_exit_policy("LONG", 100, 101, 99, 10, 0.70, "TREND_UP")
    strong = adaptive_exit_policy("LONG", 100, 101, 99, 10, 0.85, "TREND_UP")
    assert strong.partial_threshold_r > weak.partial_threshold_r
    assert strong.action == "HOLD"


def test_range_monetizes_before_trend():
    trend = adaptive_exit_policy("LONG", 100, 102, 99, 10, 0.70, "TREND_UP")
    range_exit = adaptive_exit_policy("LONG", 100, 102, 99, 10, 0.70, "RANGE")
    assert range_exit.partial_threshold_r < trend.partial_threshold_r
    assert range_exit.action == "PARTIAL"


def test_high_vol_time_stop_is_faster():
    normal = adaptive_exit_policy("LONG", 100, 100.1, 99, 50, 0.70, "TREND_UP")
    high_vol = adaptive_exit_policy("LONG", 100, 100.1, 99, 50, 0.70, "HIGH_VOL")
    assert high_vol.time_stop_bars < normal.time_stop_bars
    assert high_vol.action == "CLOSE"


def test_long_and_short_stop_logic_are_directional():
    assert adaptive_exit_policy("LONG", 100, 98, 99, 1, 0.70, "RANGE").reason == "STOP"
    assert adaptive_exit_policy("SHORT", 100, 102, 101, 1, 0.70, "RANGE").reason == "STOP"


def test_initial_risk_anchor_survives_trailing_stop():
    decision = adaptive_exit_policy(
        "LONG", 100, 101.0, 100.5, 10, 0.70, "RANGE", risk_distance=2.0
    )
    assert decision.r_multiple == pytest.approx(0.5)
    assert decision.action == "HOLD"


def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        adaptive_exit_policy("LONG", 0, 100, 99, 1, 0.7, "RANGE")
    with pytest.raises(ValueError):
        adaptive_exit_policy("FLAT", 100, 101, 99, 1, 0.7, "RANGE")
    with pytest.raises(ValueError):
        adaptive_exit_policy("LONG", 100, 101, 99, 1, 0.7, "RANGE", risk_distance=0)
