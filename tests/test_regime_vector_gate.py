import numpy as np
import pandas as pd
import pytest

from regime_vector_gate import apply_regime_btc_gate


def context(**overrides):
    values = {
        "ema20_1h": 120.0,
        "ema50_1h": 110.0,
        "ema200_1h": 100.0,
        "adx1h": 25.0,
        "vol_regime_1h": 1.0,
        "btc_ema20_1h": 120.0,
        "btc_ema50_1h": 110.0,
        "btc_ema200_1h": 100.0,
        "btc_adx1h": 25.0,
        "btc_vol_regime_1h": 1.0,
    }
    values.update(overrides)
    return pd.DataFrame([values])


def test_uptrend_keeps_long_and_blocks_short():
    data = context()
    long_out, short_out = apply_regime_btc_gate(data, [True], [True])
    assert np.array_equal(long_out, [True])
    assert np.array_equal(short_out, [False])


def test_downtrend_keeps_short_and_blocks_long():
    data = context(
        ema20_1h=90.0,
        ema50_1h=100.0,
        ema200_1h=110.0,
        btc_ema20_1h=90.0,
        btc_ema50_1h=100.0,
        btc_ema200_1h=110.0,
    )
    long_out, short_out = apply_regime_btc_gate(data, [True], [True])
    assert np.array_equal(long_out, [False])
    assert np.array_equal(short_out, [True])


def test_btc_opposition_blocks_direction():
    data = context(
        btc_ema20_1h=90.0,
        btc_ema50_1h=100.0,
        btc_ema200_1h=110.0,
    )
    long_out, short_out = apply_regime_btc_gate(data, [True], [False])
    assert np.array_equal(long_out, [False])
    assert np.array_equal(short_out, [False])


def test_btc_range_is_permissive():
    data = context(btc_adx1h=12.0)
    long_out, short_out = apply_regime_btc_gate(data, [True], [False])
    assert np.array_equal(long_out, [True])


def test_high_volatility_blocks_entries():
    data = context(vol_regime_1h=3.1)
    long_out, short_out = apply_regime_btc_gate(data, [True], [True])
    assert np.array_equal(long_out, [False])
    assert np.array_equal(short_out, [False])


def test_missing_context_fails_with_explicit_error():
    data = context().drop(columns=["btc_adx1h"])
    with pytest.raises(KeyError, match="Regime/BTC context"):
        apply_regime_btc_gate(data, [True], [False])


def test_non_finite_context_blocks_entries():
    data = context(btc_ema20_1h=np.nan)
    long_out, short_out = apply_regime_btc_gate(data, [True], [True])
    assert np.array_equal(long_out, [False])
    assert np.array_equal(short_out, [False])
