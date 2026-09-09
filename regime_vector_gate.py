"""Vectorized entry gate for historical strategy score arrays.

The gate mirrors the fixed regime/BTC rules in ``regime_filter.py`` while
keeping the existing score calculation and risk/exit logic untouched.
Missing or non-finite context fails closed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_REQUIRED = (
    "ema20_1h",
    "ema50_1h",
    "ema200_1h",
    "adx1h",
    "vol_regime_1h",
    "btc_ema20_1h",
    "btc_ema50_1h",
    "btc_ema200_1h",
    "btc_adx1h",
    "btc_vol_regime_1h",
)


def _finite(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    return np.isfinite(frame[list(columns)].astype(float)).all(axis=1)


def apply_regime_btc_gate(
    data: pd.DataFrame,
    long_signal,
    short_signal,
) -> tuple[np.ndarray, np.ndarray]:
    """Filter directional signal masks using closed 1h asset/BTC context."""
    missing = [column for column in _REQUIRED if column not in data.columns]
    if missing:
        raise KeyError(f"Regime/BTC context ontbreekt: {missing}")

    if len(long_signal) != len(data) or len(short_signal) != len(data):
        raise ValueError("signal arrays must have the same length as data")

    frame = data
    finite = _finite(frame, _REQUIRED)

    asset_up = (
        finite
        & (frame["vol_regime_1h"].astype(float) <= 3.0)
        & (frame["adx1h"].astype(float) >= 18.0)
        & (frame["ema20_1h"].astype(float) > frame["ema50_1h"].astype(float))
        & (frame["ema50_1h"].astype(float) > frame["ema200_1h"].astype(float))
    )
    asset_down = (
        finite
        & (frame["vol_regime_1h"].astype(float) <= 3.0)
        & (frame["adx1h"].astype(float) >= 18.0)
        & (frame["ema20_1h"].astype(float) < frame["ema50_1h"].astype(float))
        & (frame["ema50_1h"].astype(float) < frame["ema200_1h"].astype(float))
    )

    btc_high_vol = finite & (frame["btc_vol_regime_1h"].astype(float) > 3.0)
    btc_up = (
        finite
        & ~btc_high_vol
        & (frame["btc_adx1h"].astype(float) >= 18.0)
        & (frame["btc_ema20_1h"].astype(float) > frame["btc_ema50_1h"].astype(float))
        & (frame["btc_ema50_1h"].astype(float) > frame["btc_ema200_1h"].astype(float))
    )
    btc_down = (
        finite
        & ~btc_high_vol
        & (frame["btc_adx1h"].astype(float) >= 18.0)
        & (frame["btc_ema20_1h"].astype(float) < frame["btc_ema50_1h"].astype(float))
        & (frame["btc_ema50_1h"].astype(float) < frame["btc_ema200_1h"].astype(float))
    )

    long_allowed = asset_up & ~btc_down & ~btc_high_vol
    short_allowed = asset_down & ~btc_up & ~btc_high_vol

    return (
        np.asarray(long_signal, dtype=bool) & long_allowed.to_numpy(dtype=bool),
        np.asarray(short_signal, dtype=bool) & short_allowed.to_numpy(dtype=bool),
    )
