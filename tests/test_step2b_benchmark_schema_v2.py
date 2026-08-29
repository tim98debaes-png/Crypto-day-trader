from pathlib import Path

import pandas as pd

from research.run_step2b_benchmark import _normalize_frame, build_symbol_features


def test_open_time_alias(tmp_path: Path):
    path = tmp_path / "BTCUSDT.jsonl"
    pd.DataFrame([{"open_time": 1777593600000, "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 10}]).to_json(path, orient="records", lines=True)
    frame = _normalize_frame(path)
    assert frame.iloc[0]["timestamp"] == pd.Timestamp("2026-05-01T00:00:00Z")


def test_mtf_features_preserve_canonical_timestamp():
    periods = 320
    timestamps = pd.date_range("2026-01-01", periods=periods, freq="5min", tz="UTC")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 10.0,
        }
    )
    features = build_symbol_features(frame)
    assert "timestamp" in features.columns
    assert features["timestamp"].notna().all()
    assert features["timestamp"].is_monotonic_increasing
