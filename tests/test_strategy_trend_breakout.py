import pandas as pd

from strategy_trend_breakout import TrendBreakoutConfig, generate_signals, signal_at


def make_data(n=100, trend=1.0):
    close = [100 + trend*i for i in range(n)]
    high = [x + 0.5 for x in close]
    low = [x - 0.5 for x in close]
    volume = [1000.0] * n
    return pd.DataFrame({"open": close, "high": high, "low": low, "close": close, "volume": volume})


def test_channel_is_shifted_and_no_lookahead():
    df = make_data()
    out = __import__("strategy_trend_breakout").indicators(df)
    assert out.loc[50, "prior_high"] == df.loc[49-19:49, "high"].max()


def test_uptrend_breakout_long_signal():
    df = make_data()
    # Force a fresh breakout after a flat-ish warm-up.
    df.loc[80, "close"] = df.loc[0:79, "high"].max() + 2
    df.loc[80, "high"] = df.loc[80, "close"] + 0.5
    sig = signal_at(df, 80)
    assert sig.direction == "LONG"
    assert sig.stop_distance > 0
    assert sig.target_distance > sig.stop_distance


def test_downtrend_breakout_short_signal():
    df = make_data(trend=-0.5)
    # A close-only breakout requires the close itself to cross the prior low.
    prior_low = df.loc[60:79, "low"].min()
    df.loc[80, "close"] = prior_low - 2
    df.loc[80, "low"] = df.loc[80, "close"] - 0.5
    sig = signal_at(df, 80)
    assert sig.direction == "SHORT"
    assert sig.stop_distance > 0


def test_low_volume_filters_breakout():
    df = make_data()
    df.loc[80, "close"] = df.loc[0:79, "high"].max() + 2
    df.loc[80, "high"] = df.loc[80, "close"] + 0.5
    df.loc[80, "volume"] = 1.0
    sig = signal_at(df, 80, TrendBreakoutConfig(min_volume_ratio=1.1))
    assert sig.direction == "FLAT"
    assert sig.reason == "volume_filter"


def test_generate_signals_has_no_future_columns():
    df = make_data()
    signals = generate_signals(df)
    assert len(signals) == len(df)
    assert list(signals.columns) == ["direction", "reason"]
