import pytest
from collections import deque
from strategy_risk_controls import RiskConfig, exceeds_correlation_limit, pearson_correlation, sector_for, sector_position_count


def test_risk_config_has_conservative_caps():
    cfg = RiskConfig()
    assert cfg.max_open_positions == 8
    assert cfg.soft_open_positions == 6
    assert cfg.max_positions_per_sector == 2
    assert cfg.max_pairwise_correlation == pytest.approx(0.75)
    assert cfg.max_total_open_risk_pct == pytest.approx(12.0)


def test_perfectly_correlated_series_are_blocked():
    histories = {
        "BTCUSDT": [100, 101, 102, 103, 104, 105],
        "ETHUSDT": [50, 50.5, 51, 51.5, 52, 52.5],
    }
    assert pearson_correlation([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert exceeds_correlation_limit("ETHUSDT", ["BTCUSDT"], histories, threshold=0.75, window=6)


def test_correlation_accepts_deque_price_history():
    histories = {
        "BTCUSDT": deque([100, 101, 102, 103, 104, 105]),
        "ETHUSDT": deque([50, 50.5, 51, 51.5, 52, 52.5]),
    }
    assert exceeds_correlation_limit("ETHUSDT", ["BTCUSDT"], histories, threshold=0.75, window=6)


def test_sector_cap_counts_known_sector():
    assert sector_for("SOLUSDT") == "L1"
    assert sector_position_count("SOLUSDT", ["ETHUSDT", "ADAUSDT"]) == 2


def test_unknown_asset_does_not_get_fabricated_sector():
    assert sector_for("UNKNOWNUSDT") == "OTHER"
