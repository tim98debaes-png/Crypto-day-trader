import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd


# Ensure the repository root is importable when pytest collects this file.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
app = importlib.import_module("app")


def make_data(rows=8):
    index = pd.date_range("2026-01-01", periods=rows, freq="5min", tz="UTC")
    close = np.full(rows, 100.0)
    open_price = np.full(rows, 100.0)
    high = np.full(rows, 100.5)
    low = np.full(rows, 99.5)
    atr = np.full(rows, 1.0)

    return pd.DataFrame(
        {
            "time": index,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.full(rows, 1000.0),
            "atr": atr,
        }
    )


def params(**overrides):
    base = {
        "family": "trend",
        "rsi_min": 50,
        "rsi_max": 70,
        "threshold": 60,
        "min_edge": 5,
        "sl_atr": 1.0,
        "rr": 2.0,
        "max_bars": 48,
        "min_stop_pct": 0.1,
        "trail_atr": 1.0,
        "trail_trigger_r": 1.0,
    }
    base.update(overrides)
    return base


def test_trailing_stop_does_not_trigger_from_same_candle_high():
    data = make_data(6)
    # Signal on candle 0 -> entry at candle 1.
    # Candle 2 reaches the trailing trigger and trades below the newly
    # calculated trailing stop. The new stop must not be usable inside
    # candle 2. max_bars=1 then forces the corrected implementation to
    # exit at candle 2 close instead of at the newly created stop.
    data.loc[2, "high"] = 101.5
    data.loc[2, "low"] = 100.4
    data.loc[2, "close"] = 100.0

    app.make_signals = lambda _data, _params: (
        np.array([100, 0, 0, 0, 0, 0], dtype=np.int16),
        np.zeros(6, dtype=np.int16),
    )

    result = app.run_backtest(
        data,
        params(rr=10.0, max_bars=1),
        "Normaal",
        1000.0,
        1.0,
        0.1,
        0.0,
        "LONG",
        return_pnls=True,
    )

    assert result["trades"] == 1
    # The old same-candle trailing implementation would exit around 100.5
    # and realize a profit. The corrected implementation exits at close=100
    # and therefore realizes only the trading costs.
    assert result["pnls"][0] < 0


def test_end_of_dataset_open_position_is_realized():
    data = make_data(6)
    data.loc[2:, "close"] = 105.0
    data.loc[2:, "open"] = 105.0
    data.loc[2:, "high"] = 105.5
    data.loc[2:, "low"] = 104.5

    app.make_signals = lambda _data, _params: (
        np.array([100, 0, 0, 0, 0, 0], dtype=np.int16),
        np.zeros(6, dtype=np.int16),
    )

    result = app.run_backtest(
        data,
        params(max_bars=100),
        "Normaal",
        1000.0,
        1.0,
        0.1,
        0.0,
        "LONG",
        return_pnls=True,
    )

    assert result["trades"] == 1
    assert len(result["pnls"]) == 1
    assert result["return"] > 0


def test_long_and_short_stop_handling_is_symmetric():
    long_data = make_data(6)
    long_data.loc[2, "low"] = 98.0

    short_data = make_data(6)
    short_data.loc[2, "high"] = 102.0

    signal = np.array([100, 0, 0, 0, 0, 0], dtype=np.int16)
    zero = np.zeros(6, dtype=np.int16)

    long_signals = lambda _data, _params: (signal, zero)
    short_signals = lambda _data, _params: (zero, signal)

    app.make_signals = long_signals
    long_result = app.run_backtest(
        long_data,
        params(rr=10.0, trail_trigger_r=10.0),
        "Normaal",
        1000.0,
        1.0,
        0.1,
        0.0,
        "LONG",
        return_pnls=True,
    )

    app.make_signals = short_signals
    short_result = app.run_backtest(
        short_data,
        params(rr=10.0, trail_trigger_r=10.0),
        "Normaal",
        1000.0,
        1.0,
        0.1,
        0.0,
        "SHORT",
        return_pnls=True,
    )

    assert long_result["trades"] == 1
    assert short_result["trades"] == 1
    assert long_result["pnls"][0] < 0
    assert short_result["pnls"][0] < 0
