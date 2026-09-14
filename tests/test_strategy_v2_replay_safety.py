import pandas as pd

from research.strategy_v2_replay import _completed, _resample
from research.strategy_v2_metrics import build_metrics
from research.strategy_v2_monte_carlo import bootstrap_monte_carlo, trade_order_monte_carlo


def _minute_frame():
    timestamps = pd.date_range("2026-01-01T00:00:00Z", periods=12, freq="min")
    rows = []
    for i, ts in enumerate(timestamps):
        price = 100.0 + i
        rows.append({"timestamp": ts, "open": price, "high": price + 0.5, "low": price - 0.5, "close": price, "volume": 10.0})
    return pd.DataFrame(rows)


def test_completed_excludes_current_bar_and_future_bars():
    frame = _resample(_minute_frame(), "5min")
    decision_time = pd.Timestamp("2026-01-01T00:10:00Z")
    completed = _completed(frame, decision_time)
    assert completed
    assert all(pd.Timestamp(row["timestamp"]) < decision_time for row in completed)
    assert pd.Timestamp(completed[-1]["timestamp"]) == pd.Timestamp("2026-01-01T00:05:00Z")
    assert not any(pd.Timestamp(row["timestamp"]) >= decision_time for row in completed)


def test_future_candles_cannot_enter_completed_input():
    frame = _resample(_minute_frame(), "5min")
    decision_time = pd.Timestamp("2026-01-01T00:10:00Z")
    baseline = _completed(frame, decision_time)
    mutated = frame.copy()
    mutated.loc[mutated["timestamp"] >= decision_time, ["open", "high", "low", "close", "volume"]] = 999999.0
    assert _completed(mutated, decision_time) == baseline


def test_metrics_are_finite_and_include_robustness_measures():
    metrics = build_metrics([1000, 1005, 1002, 1010, 1008], [{"event": "CLOSE", "pnl": 5}, {"event": "CLOSE", "pnl": -3}])
    for key in ("max_drawdown_pct", "sharpe_ratio", "sortino_ratio", "calmar_ratio", "expectancy_per_trade", "payoff_ratio", "profit_factor"):
        assert pd.notna(metrics[key])
    assert metrics["closed_trades"] == 2
    assert metrics["max_consecutive_losses"] == 1


def test_trade_order_monte_carlo_is_deterministic():
    audit = [
        {"event": "CLOSE", "pnl": 10.0},
        {"event": "CLOSE", "pnl": -6.0},
        {"event": "CLOSE", "pnl": 4.0},
        {"event": "CLOSE", "pnl": -2.0},
    ]
    first = trade_order_monte_carlo(audit, simulations=100, seed=42)
    second = trade_order_monte_carlo(audit, simulations=100, seed=42)
    assert first == second
    assert first["trades"] == 4
    assert first["simulations"] == 100
    assert 0.0 <= first["probability_of_loss_pct"] <= 100.0


def test_bootstrap_monte_carlo_is_deterministic_and_has_variable_outcomes():
    audit = [
        {"event": "CLOSE", "pnl": 10.0},
        {"event": "CLOSE", "pnl": -6.0},
        {"event": "CLOSE", "pnl": 4.0},
        {"event": "CLOSE", "pnl": -2.0},
    ]
    first = bootstrap_monte_carlo(audit, simulations=500, seed=42)
    second = bootstrap_monte_carlo(audit, simulations=500, seed=42)
    assert first == second
    assert first["trades_per_simulation"] == 4
    assert first["simulations"] == 500
    assert first["p05_final_equity"] != first["p95_final_equity"]
    assert 0.0 <= first["probability_of_loss_pct"] <= 100.0
