from regime_filter import (
    btc_direction_allowed,
    classify_regime,
    market_direction_allowed,
)


def test_uptrend_requires_ordered_emas_and_adx():
    assert classify_regime(110, 105, 100, 18, 1.0) == "TREND_UP"
    assert classify_regime(110, 105, 100, 17.9, 1.0) == "RANGE"


def test_downtrend_requires_ordered_emas_and_adx():
    assert classify_regime(90, 95, 100, 20, 1.0) == "TREND_DOWN"


def test_high_volatility_is_risk_off():
    assert classify_regime(110, 105, 100, 30, 3.01) == "HIGH_VOL"


def test_range_blocks_directional_entries():
    assert not market_direction_allowed("LONG", "RANGE")
    assert not market_direction_allowed("SHORT", "RANGE")
    assert market_direction_allowed("LONG", "TREND_UP")
    assert market_direction_allowed("SHORT", "TREND_DOWN")


def test_btc_filter_blocks_opposed_direction():
    assert not btc_direction_allowed("LONG", "TREND_DOWN")
    assert not btc_direction_allowed("SHORT", "TREND_UP")
    assert btc_direction_allowed("LONG", "TREND_UP")
    assert btc_direction_allowed("SHORT", "TREND_DOWN")
    assert not btc_direction_allowed("LONG", "HIGH_VOL")
    assert not btc_direction_allowed("SHORT", "UNKNOWN")
