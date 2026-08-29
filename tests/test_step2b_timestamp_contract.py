from research.run_step2b_benchmark import build_symbol_features
import pandas as pd


def test_mtf_features_preserve_canonical_timestamp():
    periods = 320
    timestamps = pd.date_range("2026-01-01", periods=periods, freq="5min", tz="UTC")
    frame = pd.DataFrame({
        "timestamp": timestamps,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.0,
        "volume": 10.0,
    })
    features = build_symbol_features(frame)
    assert "timestamp" in features.columns
    assert features["timestamp"].notna().all()
    assert features["timestamp"].is_monotonic_increasing
