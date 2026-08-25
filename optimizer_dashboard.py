"""Application-facing helpers for the Phase 15 optimizer.

The helpers keep Streamlit concerns out of the optimization engine and expose
only deterministic, serializable data to the dashboard.
"""
from __future__ import annotations

from typing import Iterable

from strategy_optimizer import OptimizationResult, StrategyOptimizer


def build_signal_strategy_factory() -> callable:
    """Create the baseline score-threshold strategy used by the optimizer UI.

    Candles must provide long_score, short_score and stop_distance. The
    optimizer varies signal_threshold and rr; no live orders are involved.
    """
    def factory(params: dict):
        threshold = float(params["signal_threshold"])
        rr = float(params["rr"])

        def strategy(candle: dict):
            long_score = float(candle.get("long_score", 0) or 0)
            short_score = float(candle.get("short_score", 0) or 0)
            stop_distance = float(candle.get("stop_distance", 0) or 0)
            if stop_distance <= 0 or rr <= 0:
                return {"action": "WAIT"}
            if long_score >= threshold and long_score > short_score:
                return {"action": "LONG", "stop_distance": stop_distance, "rr": rr}
            if short_score >= threshold and short_score > long_score:
                return {"action": "SHORT", "stop_distance": stop_distance, "rr": rr}
            return {"action": "WAIT"}
        return strategy
    return factory


def result_rows(results: Iterable[OptimizationResult]) -> list[dict]:
    rows = []
    for rank, result in enumerate(results, start=1):
        summary = result.summary
        rows.append({
            "rank": rank,
            **result.parameters,
            "score": round(result.score, 6),
            "return_pct": summary.get("return_pct", 0.0),
            "max_drawdown_pct": summary.get("max_drawdown_pct", 0.0),
            "profit_factor": summary.get("profit_factor", 0.0),
            "closed_trades": summary.get("closed_trades", 0),
            "win_rate_pct": summary.get("win_rate_pct", 0.0),
        })
    return rows


def optimize_candles(candles: Iterable[dict], threshold_values: Iterable[float], rr_values: Iterable[float], top_n: int = 10) -> list[dict]:
    grid = {"signal_threshold": list(threshold_values), "rr": list(rr_values)}
    results = StrategyOptimizer().optimize(candles, grid, build_signal_strategy_factory(), top_n=top_n)
    return result_rows(results)


def walk_forward_candles(candles: Iterable[dict], threshold_values: Iterable[float], rr_values: Iterable[float], train_ratio: float = 0.7, top_n: int = 10) -> dict:
    grid = {"signal_threshold": list(threshold_values), "rr": list(rr_values)}
    return StrategyOptimizer().walk_forward(candles, grid, build_signal_strategy_factory(), train_ratio=train_ratio, top_n=top_n)
