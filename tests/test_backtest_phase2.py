import importlib

import numpy as np
import pandas as pd


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
    # Candle 2 reaches the trailing trigger, but also drops below the
    # newly calculated trailing stop. Phase 2 must not use that new stop
    # to exit inside candle 2.
    data.loc[2, "high"] = 103.0
    data.loc[2, "low"] = 100.8
    data.loc[3, "low"] = 100.8

    app.make_signals = lambda _data, _params: (
        np.array([100, 0, 0, 0, 0, 0], dtype=np.int16),
        np.zeros(6, dtype=np.int16),
    )

    result = app.run_backtest(
        data,
        params(),
        "Normaal",
        1000.0,
        1.0,
        0.1,
        0.0,
        "LONG",
        return_pnls=True,
    )

    # The position should remain open through candle 2 rather than being
    # stopped by a trailing level created from candle 2's own high.
    assert result["trades"] == 1


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
    app.make_signals = lambda _data, _params: (signal, zero)

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
