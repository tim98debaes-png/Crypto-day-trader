"""Benchmark Strategy V3 against locked V2 and run chronological OOS slices."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.paper_parity_replay import ReplayConfig, load_dataset
from research.strategy_v2_replay import run_v2
from research.strategy_v3_replay import run_v3
from strategy_v3 import V3Config


def _metric_block(report: dict) -> dict:
    result = report["result"]
    metrics = report["diagnostics"]["robustness_metrics"]
    return {
        "final_equity": result["final_equity"],
        "pnl": result["pnl"],
        "return_pct": result["return_pct"],
        "max_drawdown_pct": result["max_drawdown_pct"],
        "closed_trades": result["closed_trades"],
        "win_rate_pct": result["win_rate_pct"],
        "profit_factor": result["profit_factor"],
        "sharpe_ratio": metrics["sharpe_ratio"],
        "sortino_ratio": metrics["sortino_ratio"],
        "calmar_ratio": metrics["calmar_ratio"],
        "expectancy_per_trade": metrics["expectancy_per_trade"],
        "payoff_ratio": metrics["payoff_ratio"],
        "max_consecutive_losses": metrics["max_consecutive_losses"],
    }


def _slice_frames(frames: dict[str, pd.DataFrame], start: pd.Timestamp, end: pd.Timestamp) -> dict[str, pd.DataFrame]:
    return {s: f[(f["timestamp"] >= start) & (f["timestamp"] < end)].copy() for s, f in frames.items()}


def run_benchmark(frames: dict[str, pd.DataFrame], config: ReplayConfig, v3: V3Config, folds: int = 4) -> dict:
    v2_result, v2_diag = run_v2(frames, config)
    v3_result, v3_diag = run_v3(frames, config, v3)
    v2_report = {"result": v2_result, "diagnostics": v2_diag}
    v3_report = {"result": v3_result, "diagnostics": v3_diag}
    v2_metrics = _metric_block(v2_report)
    v3_metrics = _metric_block(v3_report)
    delta = {k: v3_metrics[k] - v2_metrics[k] for k in v2_metrics if isinstance(v2_metrics[k], (int, float))}

    timestamps = sorted(set().union(*(set(f["timestamp"]) for f in frames.values())))
    start, end = min(timestamps), max(timestamps) + pd.Timedelta(minutes=1)
    boundaries = pd.date_range(start=start, end=end, periods=folds + 1, tz="UTC")
    oos = []
    for i in range(folds):
        fold_start, fold_end = boundaries[i], boundaries[i + 1]
        fold_frames = _slice_frames(frames, fold_start, fold_end)
        if not all(len(f) >= 4000 for f in fold_frames.values()):
            continue
        result, diag = run_v3(fold_frames, config, v3)
        metrics = _metric_block({"result": result, "diagnostics": diag})
        oos.append({"fold": i + 1, "start": str(fold_start), "end": str(fold_end), "metrics": metrics, "regime_trade_counts": diag.get("regime_trade_counts", {}), "exits": diag.get("exits", {}), "bootstrap_monte_carlo": diag.get("bootstrap_monte_carlo", {})})
    passed = [f for f in oos if f["metrics"]["profit_factor"] >= 1.0 and f["metrics"]["expectancy_per_trade"] > 0 and f["metrics"]["max_drawdown_pct"] <= 15.0 and f["metrics"]["closed_trades"] >= 20]
    promotion = {"eligible": bool(oos) and len(passed) / len(oos) >= 0.75 and sum(f["metrics"]["expectancy_per_trade"] for f in oos) / len(oos) > 0 and sum(f["metrics"]["profit_factor"] for f in oos) / len(oos) >= 1.0, "folds_passed": len(passed), "folds_total": len(oos), "criteria": {"min_profit_factor": 1.0, "min_expectancy": 0.0, "max_drawdown_pct": 15.0, "min_trades": 20, "min_pass_ratio": 0.75}}
    return {"schema_version": 1, "status": "EXECUTION_COMPLETE", "period": {"start": str(start), "end": str(end), "interval": "1m"}, "baseline": "V2_LOCKED", "v2": v2_metrics, "v3": v3_metrics, "v3_minus_v2": delta, "v3_diagnostics": v3_diag, "oos_fixed_parameter_slices": oos, "promotion_gate": promotion}


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--data", required=True); p.add_argument("--output", required=True); a = p.parse_args()
    frames = load_dataset(Path(a.data))
    report = run_benchmark(frames, ReplayConfig(capital=1000.0, risk_pct=0.5, fee_pct=0.1, slippage_pct=0.02, max_daily_loss_pct=3.0), V3Config(), folds=4)
    out = Path(a.output); out.mkdir(parents=True, exist_ok=True); (out / "strategy_v3_benchmark.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"); print(json.dumps(report, indent=2, default=str))

if __name__ == "__main__": main()
