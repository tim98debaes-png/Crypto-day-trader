import pandas as pd

from research.paper_parity_replay import _btc_ok, _regime_ok, _stop_distance, _volatility
from collections import deque


def _row(**values):
    return pd.Series(values)


def test_long_regime_requires_closed_uptrend_and_adx():
    row = _row(ema20_1h=110, ema50_1h=105, ema200_1h=100, adx1h=20, vol_regime_1h=1.5)
    assert _regime_ok(row, "LONG") is True
    assert _regime_ok(row, "SHORT") is False


def test_high_volatility_blocks_both_regime_directions():
    row = _row(ema20_1h=110, ema50_1h=105, ema200_1h=100, adx1h=30, vol_regime_1h=3.5)
    assert _regime_ok(row, "LONG") is False
    assert _regime_ok(row, "SHORT") is False


def test_btc_filter_blocks_only_opposite_trend_or_high_vol():
    up = _row(btc_ema20_1h=110, btc_ema50_1h=105, btc_ema200_1h=100, btc_adx1h=25, btc_vol_regime_1h=1.5)
    down = _row(btc_ema20_1h=90, btc_ema50_1h=95, btc_ema200_1h=100, btc_adx1h=25, btc_vol_regime_1h=1.5)
    rng = _row(btc_ema20_1h=101, btc_ema50_1h=100, btc_ema200_1h=99, btc_adx1h=10, btc_vol_regime_1h=1.5)
    high = _row(btc_ema20_1h=110, btc_ema50_1h=105, btc_ema200_1h=100, btc_adx1h=25, btc_vol_regime_1h=3.5)
    assert _btc_ok(up, "LONG") is True
    assert _btc_ok(up, "SHORT") is False
    assert _btc_ok(down, "SHORT") is True
    assert _btc_ok(down, "LONG") is False
    assert _btc_ok(rng, "LONG") is True
    assert _btc_ok(rng, "SHORT") is True
    assert _btc_ok(high, "LONG") is False
    assert _btc_ok(high, "SHORT") is False


def test_stop_distance_has_live_paper_floor():
    assert _stop_distance(100.0, 0.01) == 0.6
    assert _stop_distance(100.0, 1.0) > 0.6


def test_volatility_uses_only_available_history():
    history = deque([100.0, 100.2, 99.8, 100.0], maxlen=20)
    expected = max(abs(100.2 / 100.0 - 1) * 100, abs(99.8 / 100.2 - 1) * 100, abs(100.0 / 99.8 - 1) * 100)
    assert abs(_volatility(history) - expected) < 1e-12
