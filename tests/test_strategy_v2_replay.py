import pandas as pd

from research.strategy_v2_replay import _completed, _resample


def _frame(periods=12):
    ts = pd.date_range("2026-01-01", periods=periods, freq="min", tz="UTC")
    return pd.DataFrame({
        "timestamp": ts,
        "open": range(100, 100 + periods),
        "high": range(101, 101 + periods),
        "low": range(99, 99 + periods),
        "close": range(100, 100 + periods),
        "volume": [10.0] * periods,
    })


def test_resample_uses_ohlcv_aggregation():
    out = _resample(_frame(), "5min")
    assert len(out) == 3
    assert out.iloc[0]["open"] == 100
    assert out.iloc[0]["high"] == 105
    assert out.iloc[0]["low"] == 99
    assert out.iloc[0]["close"] == 104
    assert out.iloc[0]["volume"] == 50


def test_completed_excludes_current_bucket():
    frame = _resample(_frame(), "5min")
    current = pd.Timestamp("2026-01-01T00:10:00Z")
    completed = _completed(frame, current, count=30)
    assert [row["timestamp"] for row in completed] == list(frame[frame["timestamp"] < current]["timestamp"])
    assert all(row["timestamp"] < current for row in completed)
