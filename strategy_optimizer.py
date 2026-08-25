"""Deterministic parameter optimization for the historical backtester."""
from __future__ import annotations
from dataclasses import dataclass
from itertools import product
from typing import Callable, Iterable

from backtest_engine import HistoricalBacktester

StrategyFactory = Callable[[dict], Callable[[dict], dict | None]]

@dataclass(frozen=True)
class OptimizationResult:
    parameters: dict
    summary: dict
    score: float

class StrategyOptimizer:
    def __init__(self, backtester: HistoricalBacktester | None = None):
        self.backtester = backtester or HistoricalBacktester()

    @staticmethod
    def score(summary: dict) -> float:
        ret = float(summary.get("return_pct", 0.0))
        dd = float(summary.get("max_drawdown_pct", 0.0))
        pf = float(summary.get("profit_factor", 0.0))
        if pf == float("inf"):
            pf = 10.0
        return ret + min(pf, 10.0) * 2.0 - dd * 0.75

    def optimize(self, candles: Iterable[dict], parameter_grid: dict[str, Iterable], strategy_factory: StrategyFactory, top_n: int = 10) -> list[OptimizationResult]:
        if top_n < 1:
            raise ValueError("top_n must be positive")
        names = list(parameter_grid)
        values = [list(parameter_grid[n]) for n in names]
        if not names or any(not v for v in values):
            raise ValueError("parameter_grid must contain non-empty parameter options")
        data = [dict(c) for c in candles]
        results = []
        for combo in product(*values):
            params = dict(zip(names, combo))
            summary = self.backtester.run(data, strategy_factory(params)).summary()
            results.append(OptimizationResult(params, summary, self.score(summary)))
        results.sort(key=lambda r: (-r.score, r.summary.get("max_drawdown_pct", 0.0), str(sorted(r.parameters.items()))))
        return results[:top_n]

    def walk_forward(self, candles: Iterable[dict], parameter_grid: dict[str, Iterable], strategy_factory: StrategyFactory, train_ratio: float = 0.7, top_n: int = 10) -> dict:
        if not 0.5 <= train_ratio < 1.0:
            raise ValueError("train_ratio must be >= 0.5 and < 1")
        data = [dict(c) for c in candles]
        split = int(len(data) * train_ratio)
        if split < 2 or split >= len(data):
            raise ValueError("not enough candles for train/test split")
        ranked = self.optimize(data[:split], parameter_grid, strategy_factory, top_n)
        candidates = []
        for result in ranked:
            test_summary = self.backtester.run(data[split:], strategy_factory(result.parameters)).summary()
            candidates.append({"parameters": result.parameters, "train": result.summary, "train_score": result.score, "test": test_summary, "test_score": self.score(test_summary)})
        candidates.sort(key=lambda x: (-x["test_score"], x["test"].get("max_drawdown_pct", 0.0)))
        return {"train_candles": split, "test_candles": len(data) - split, "candidates": candidates}
