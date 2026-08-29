from pathlib import Path

import pandas as pd

from research.run_step2b_benchmark import _normalize_frame


def test_normalize_frame_accepts_canonical_timestamp(tmp_path: Path):
    path = tmp_path / "BTCUSDT.jsonl"
    pd.DataFrame([{"timestamp": 1777593600000, "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 10}]).to_json(path, orient="records", lines=True)
    frame = _normalize_frame(path)
    assert frame.iloc[0]["timestamp"] == pd.Timestamp("2026-05-01T00:00:00Z")


def test_normalize_frame_accepts_open_time_alias(tmp_path: Path):
    path = tmp_path / "BTCUSDT.jsonl"
    pd.DataFrame([{"open_time": 1777593600000, "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 10}]).to_json(path, orient="records", lines=True)
    frame = _normalize_frame(path)
    assert frame.iloc[0]["timestamp"] == pd.Timestamp("2026-05-01T00:00:00Z")
