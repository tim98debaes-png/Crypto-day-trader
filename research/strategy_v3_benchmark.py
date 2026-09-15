"""Fast benchmark for Strategy V3 against the locked V2 baseline.

The benchmark is deliberately structured so the expensive replays can run in
parallel. V2 is a locked historical baseline, so replaying it on every V3
benchmark run only burns CPU without changing the comparison baseline.
"""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from research.paper_parity_replay import ReplayConfig, load_dataset
from research.strategy_v3_replay import run_v3
from strategy_v3 import V3Config


LOCKED_V2 = {
    "final_equity": 996.6808353,
    "pnl": -3.3191647,
    "return_pct": -0.33191647,
    "max_drawdown_pct": 3.28439725,
    "closed_trades": 196,
    "win_rate_pct": 46.93877551,
    "profit_factor": 0.65816121,
    "sharpe_ratio": -0.0813581085,
    "sortino_ratio": -0.1217658539,
    "calmar_ratio": -0.3989716786,
    "expectancy_per_trade": -0.3973042607,
    "payoff_ratio": 0.7440083,
    "max_consecutive_losses": 8,
}

_WORKER_FRAMES: dict[str, pd.DataFrame] | None = None
_WORKER_CONFIG: ReplayConfig | None = None
_WORKER_V3: V3Config | None = None


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


def _init_worker() -> None:
    # Intentionally empty: with fork the workers inherit the parent's
    # read-only dataframe/config globals copy-on-write, avoiding serialization.
    return None


def _run_full_v3() -> tuple[str, dict, dict]:
    assert _WORKER_FRAMES is not None and _WORKER_CONFIG is not None and _WORKER_V3 is not None
    result, diag = run_v3(_WORKER_FRAMES, _WORKER_CONFIG, _WORKER_V3)
    return "full", result, diag


def _run_oos(payload: tuple[int, pd.Timestamp, pd.Timestamp]) -> tuple[str, int, str, str, dict, dict]:
    assert _WORKER_FRAMES is not None and _WORKER_CONFIG is not None and _WORKER_V3 is not None
    fold, start, end = payload
    fold_frames = _slice_frames(_WORKER_FRAMES, start, end)
    import research.strategy_v3_replay as replay_module
    original_bootstrap = replay_module.bootstrap_monte_carlo
    replay_module.bootstrap_monte_carlo = lambda *args, **kwargs: {"status": "SKIPPED_OOS"}
    try:
        result, diag = run_v3(fold_frames, _WORKER_CONFIG, _WORKER_V3)
    finally:
        replay_module.bootstrap_monte_carlo = original_bootstrap
    return "oos", fold, str(start), str(end), result, diag


def _run_parallel(frames: dict[str, pd.DataFrame], config: ReplayConfig, v3: V3Config, payloads: list[tuple[int, pd.Timestamp, pd.Timestamp]]) -> tuple[tuple[dict, dict], list[dict]]:
    """Run full V3 and OOS replays concurrently using forked shared memory."""
    if os.name != "posix":
        result, diag = run_v3(frames, config, v3)
        oos = []
        for fold, start, end in payloads:
            fold_frames = _slice_frames(frames, start, end)
            import research.strategy_v3_replay as replay_module
            original_bootstrap = replay_module.bootstrap_monte_carlo
            replay_module.bootstrap_monte_carlo = lambda *args, **kwargs: {"status": "SKIPPED_OOS"}
            try:
                r, d = run_v3(fold_frames, config, v3)
            finally:
                replay_module.bootstrap_monte_carlo = original_bootstrap
            oos.append({"fold": fold, "start": str(start), "end": str(end), "result": r, "diagnostics": d})
        return (result, diag), oos

    import multiprocessing as mp
    global _WORKER_FRAMES, _WORKER_CONFIG, _WORKER_V3
    _WORKER_FRAMES, _WORKER_CONFIG, _WORKER_V3 = frames, config, v3
    ctx = mp.get_context("fork")
    max_workers = min(len(payloads) + 1, max(2, (os.cpu_count() or 2) - 1))
    with ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx, initializer=_init_worker) as pool:
        futures = [pool.submit(_run_full_v3)] + [pool.submit(_run_oos, payload) for payload in payloads]
        full = futures[0].result()
        oos_results = [future.result() for future in futures[1:]]

    _, full_result, full_diag = full
    oos = []
    for item in sorted(oos_results, key=lambda x: x[1]):
        _, fold, start, end, result, diag = item
        oos.append({"fold": fold, "start": start, "end": end, "result": result, "diagnostics": diag})
    return (full_result, full_diag), oos


def run_benchmark(frames: dict[str, pd.DataFrame], config: ReplayConfig, v3: V3Config, folds: int = 3) -> dict:
    if folds < 3:
        raise ValueError("folds must be >= 3 for the promotion gate")

    timestamps = sorted(set().union(*(set(f["timestamp"]) for f in frames.values())))
    start, end = min(timestamps), max(timestamps) + pd.Timedelta(minutes=1)
    boundaries = pd.date_range(start=start, end=end, periods=folds + 1, tz="UTC")
    payloads = []
    for i in range(folds):
        fold_start, fold_end = boundaries[i], boundaries[i + 1]
        fold_frames = _slice_frames(frames, fold_start, fold_end)
        if all(len(f) >= 4000 for f in fold_frames.values()):
            payloads.append((i + 1, fold_start, fold_end))

    (v3_result, v3_diag), oos_raw = _run_parallel(frames, config, v3, payloads)
    v3_metrics = _metric_block({"result": v3_result, "diagnostics": v3_diag})
    delta = {k: v3_metrics[k] - LOCKED_V2[k] for k in LOCKED_V2 if isinstance(LOCKED_V2[k], (int, float))}

    oos = []
    for fold in oos_raw:
        metrics = _metric_block({"result": fold["result"], "diagnostics": fold["diagnostics"]})
        oos.append({
            "fold": fold["fold"],
            "start": fold["start"],
            "end": fold["end"],
            "metrics": metrics,
            "regime_trade_counts": fold["diagnostics"].get("regime_trade_counts", {}),
            "exits": fold["diagnostics"].get("exits", {}),
        })

    passed = [f for f in oos if f["metrics"]["profit_factor"] >= 1.0 and f["metrics"]["expectancy_per_trade"] > 0 and f["metrics"]["max_drawdown_pct"] <= 15.0 and f["metrics"]["closed_trades"] >= 20]
    promotion = {
        "eligible": bool(oos) and len(passed) / len(oos) >= 0.75 and sum(f["metrics"]["expectancy_per_trade"] for f in oos) / len(oos) > 0 and sum(f["metrics"]["profit_factor"] for f in oos) / len(oos) >= 1.0,
        "folds_passed": len(passed),
        "folds_total": len(oos),
        "criteria": {"min_profit_factor": 1.0, "min_expectancy": 0.0, "max_drawdown_pct": 15.0, "min_trades": 20, "min_pass_ratio": 0.75},
    }
    return {
        "schema_version": 2,
        "status": "EXECUTION_COMPLETE",
        "period": {"start": str(start), "end": str(end), "interval": "1m"},
        "baseline": "V2_LOCKED",
        "v2": LOCKED_V2,
        "v3": v3_metrics,
        "v3_minus_v2": delta,
        "v3_diagnostics": v3_diag,
        "oos_fixed_parameter_slices": oos,
        "promotion_gate": promotion,
        "performance": {
            "parallel_replays": len(payloads) + 1,
            "oos_bootstrap": "disabled",
            "v2_replay": "reused_locked_baseline",
        },
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--folds", type=int, default=3)
    a = p.parse_args()
    frames = load_dataset(Path(a.data))
    report = run_benchmark(
        frames,
        ReplayConfig(capital=1000.0, risk_pct=0.5, fee_pct=0.1, slippage_pct=0.02, max_daily_loss_pct=3.0),
        V3Config(),
        folds=a.folds,
    )
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / "strategy_v3_benchmark.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
