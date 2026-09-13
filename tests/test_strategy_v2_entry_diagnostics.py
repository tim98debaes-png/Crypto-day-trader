import pandas as pd

from research.strategy_v2_entry_diagnostics import REQUIRED_HISTORY, run_diagnostics


def _frame(periods=600):
    ts = pd.date_range("2026-01-01", periods=periods, freq="min", tz="UTC")
    close = [100.0 + i * 0.01 for i in range(periods)]
    return pd.DataFrame({"timestamp": ts, "open": close, "high": [v + 0.1 for v in close], "low": [v - 0.1 for v in close], "close": close, "volume": [10.0] * periods})


def test_diagnostics_requires_real_mtf_history_and_emits_funnel():
    report = run_diagnostics({"BTCUSDT": _frame(), "ETHUSDT": _frame()}, stride=20)
    assert report["status"] == "EXECUTION_COMPLETE"
    assert report["sampling"]["required_mtf_history"] == REQUIRED_HISTORY
    for direction in ("LONG", "SHORT"):
        d = report["directions"][direction]
        assert set(d["failed_at"]) == {"trend", "structure", "pullback_trigger", "participation", "btc_compatible"}
        assert sum(d["score_distribution"].values()) == d["eligible"]
