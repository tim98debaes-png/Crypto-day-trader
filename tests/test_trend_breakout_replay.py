import pandas as pd

from research.trend_breakout_replay import ReplayConfig, replay_ohlcv
from strategy_trend_breakout import TrendBreakoutConfig


def _base(n=90):
    close = [100.0 + i * 0.05 for i in range(n)]
    return pd.DataFrame({"open": close, "high": [x + 0.5 for x in close], "low": [x - 0.5 for x in close], "close": close, "volume": [1000.0] * n})


def test_replay_uses_next_bar_open_and_records_costs():
    df = _base()
    prior_high = df.loc[60:79, "high"].max()
    df.loc[80, "close"] = prior_high + 2.0
    df.loc[80, "high"] = df.loc[80, "close"] + 0.5
    df.loc[81, "open"] = df.loc[80, "close"] + 1.0
    df.loc[81, "close"] = df.loc[81, "open"] + 1.0
    result = replay_ohlcv(df, TrendBreakoutConfig(min_atr_pct=0.1), ReplayConfig(fee_pct=0.1, slippage_pct=0.02))
    assert result["closed_trades"] >= 1
    trade = result["trades"][0]
    assert trade["entry_index"] == 81
    assert result["fees_and_slippage_included"] is True


def test_ambiguous_bar_is_stop_first():
    df = _base()
    prior_high = df.loc[60:79, "high"].max()
    df.loc[80, "close"] = prior_high + 2.0
    df.loc[80, "high"] = df.loc[80, "close"] + 0.5
    df.loc[81, "open"] = df.loc[80, "close"]
    df.loc[81, "low"] = df.loc[81, "open"] - 20.0
    df.loc[81, "high"] = df.loc[81, "open"] + 20.0
    result = replay_ohlcv(df, TrendBreakoutConfig(min_atr_pct=0.1), ReplayConfig(fee_pct=0.0, slippage_pct=0.0))
    assert result["closed_trades"] >= 1
    assert result["trades"][0]["reason"] == "SL"
