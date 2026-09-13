from datetime import datetime, timedelta, timezone

import pandas as pd

from research.strategy_v3_replay import _completed, run_v3
from research.paper_parity_replay import ReplayConfig
from strategy_v3 import V3Config


def _frame(seed: float, n: int = 800) -> pd.DataFrame:
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        price = seed * (1.0 + 0.0002 * i + 0.002 * ((i % 17) - 8) / 8.0)
        rows.append({
            "timestamp": start + timedelta(minutes=i),
            "open": price,
            "high": price * 1.001,
            "low": price * 0.999,
            "close": price * (1.0 + 0.0001 * ((i % 5) - 2)),
            "volume": 1000.0 + i,
        })
    return pd.DataFrame(rows)


def test_completed_excludes_decision_bar_and_future_bars():
    frame = _frame(100.0)
    series = frame.assign(timestamp=pd.to_datetime(frame["timestamp"]))
    decision = series.iloc[200]["timestamp"]
    result = _completed(series, decision, count=60)
    assert result
    assert all(pd.Timestamp(row["timestamp"]) < decision for row in result)
    assert max(pd.Timestamp(row["timestamp"]) for row in result) < decision


def test_v3_replay_is_deterministic_and_schema_safe():
    frames = {"BTCUSDT": _frame(100.0), "ETHUSDT": _frame(50.0), "SOLUSDT": _frame(25.0)}
    cfg = ReplayConfig(capital=1000.0, risk_pct=0.5, fee_pct=0.1, slippage_pct=0.02, max_daily_loss_pct=3.0)
    v3 = V3Config(min_setup_score=0.55, max_open_positions=2)
    result_a, diag_a = run_v3(frames, cfg, v3)
    result_b, diag_b = run_v3(frames, cfg, v3)
    assert result_a == result_b
    assert diag_a["robustness_metrics"] == diag_b["robustness_metrics"]
    assert diag_a["max_open_positions"] <= 2
    assert diag_a["strategy"] == "V3"
    assert "bootstrap_monte_carlo" in diag_a
