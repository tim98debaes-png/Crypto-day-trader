import numpy as np
import pandas as pd

from research.mtf_features import add_btc_context
from research.run_step2b_benchmark import _regime_masks, _btc_masks


def _features():
    ts = pd.date_range("2026-01-01", periods=4, freq="1h", tz="UTC")
    asset = pd.DataFrame({
        "timestamp": ts,
        "ema20_1h": [3., 4., 5., 6.],
        "ema50_1h": [2., 3., 4., 5.],
        "ema200_1h": [1., 2., 3., 4.],
        "adx1h": [20., 20., 20., 20.],
        "vol_regime_1h": [1., 1., 1., 1.],
    })
    return asset


def test_regime_masks_require_directional_closed_context():
    up, down = _regime_masks(_features())
    assert up.tolist() == [True, True, True, True]
    assert not down.any()


def test_btc_masks_block_high_vol():
    x = _features().rename(columns={
        "ema20_1h": "btc_ema20_1h",
        "ema50_1h": "btc_ema50_1h",
        "ema200_1h": "btc_ema200_1h",
        "adx1h": "btc_adx1h",
        "vol_regime_1h": "btc_vol_regime_1h",
    })
    up, down, high = _btc_masks(x)
    assert up.all()
    assert not down.any()
    assert not high.any()
    x.loc[2, "btc_vol_regime_1h"] = 3.1
    up, _, high = _btc_masks(x)
    assert not up[2]
    assert high[2]


def test_btc_context_uses_next_hour_as_availability_boundary():
    asset = pd.DataFrame({"timestamp": pd.to_datetime(["2026-01-01 00:30", "2026-01-01 01:30"], utc=True).astype("datetime64[ms, UTC]")})
    btc = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 01:00"], utc=True).astype("datetime64[us, UTC]"),
        "ema20_1h": [10., 20.], "ema50_1h": [9., 19.],
        "ema200_1h": [8., 18.], "adx1h": [20., 21.],
        "vol_regime_1h": [1., 1.],
    })
    out = add_btc_context(asset, btc)
    assert np.isnan(out.loc[0, "btc_ema20_1h"])
    assert out.loc[1, "btc_ema20_1h"] == 10.
    assert str(out["timestamp"].dtype) == "datetime64[ns, UTC]"
