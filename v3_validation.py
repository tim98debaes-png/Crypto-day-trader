"""Validation gates for Strategy V3 candidates.

The key rule is that discovery and acceptance are separated. A candidate must
survive out-of-sample folds and risk gates; a single profitable backtest is not
sufficient for promotion.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Callable, Iterable, Sequence


@dataclass(frozen=True)
class FoldResult:
    fold: int
    train_size: int
    test_size: int
    train_score: float
    test_return_pct: float
    test_profit_factor: float
    test_drawdown_pct: float
    test_expectancy: float
    test_trades: int


@dataclass(frozen=True)
class PromotionDecision:
    eligible: bool
    reasons: tuple[str, ...]
    folds_passed: int
    folds_total: int


def objective(summary: dict) -> float:
    """Risk-adjusted research objective; avoids rewarding trade-count inflation."""
    ret = float(summary.get("return_pct", 0.0))
    pf = float(summary.get("profit_factor", 0.0))
    dd = float(summary.get("max_drawdown_pct", 0.0))
    exp = float(summary.get("expectancy_per_trade", 0.0))
    trades = int(summary.get("closed_trades", summary.get("trades", 0)))
    if trades < 20:
        return -100.0 + trades
    return ret + min(max(pf, 0.0), 5.0) * 2.0 + exp * 10.0 - dd * 1.25


def walk_forward(
    candles: Sequence[dict],
    train_test_runner: Callable[[Sequence[dict], Sequence[dict]], tuple[dict, dict]],
    *,
    folds: int = 4,
    train_ratio: float = 0.65,
) -> list[FoldResult]:
    if folds < 2 or len(candles) < 100:
        raise ValueError("insufficient data for walk-forward validation")
    if not 0.5 <= train_ratio < 0.9:
        raise ValueError("train_ratio must be between 0.5 and 0.9")
    n = len(candles)
    fold_size = n // folds
    results: list[FoldResult] = []
    for i in range(folds):
        test_start = i * fold_size
        test_end = n if i == folds - 1 else (i + 1) * fold_size
        train_end = test_start
        if train_end < 20:
            train_end = min(n, max(20, int(test_end * train_ratio)))
        train_start = max(0, train_end - max(20, int((test_end - test_start) / max(1e-9, 1 - train_ratio) * train_ratio)))
        train = candles[train_start:train_end]
        test = candles[test_start:test_end]
        if len(train) < 20 or len(test) < 10:
            continue
        train_summary, test_summary = train_test_runner(train, test)
        results.append(FoldResult(
            fold=i + 1,
            train_size=len(train),
            test_size=len(test),
            train_score=objective(train_summary),
            test_return_pct=float(test_summary.get("return_pct", 0.0)),
            test_profit_factor=float(test_summary.get("profit_factor", 0.0)),
            test_drawdown_pct=float(test_summary.get("max_drawdown_pct", 0.0)),
            test_expectancy=float(test_summary.get("expectancy_per_trade", 0.0)),
            test_trades=int(test_summary.get("closed_trades", test_summary.get("trades", 0))),
        ))
    return results


def promotion_gate(
    folds: Sequence[FoldResult],
    *,
    min_profit_factor: float = 1.0,
    min_expectancy: float = 0.0,
    max_drawdown_pct: float = 15.0,
    min_trades_per_fold: int = 20,
    min_pass_ratio: float = 0.75,
) -> PromotionDecision:
    if not folds:
        return PromotionDecision(False, ("NO_FOLDS",), 0, 0)
    passed = [
        f for f in folds
        if f.test_profit_factor >= min_profit_factor
        and f.test_expectancy > min_expectancy
        and f.test_drawdown_pct <= max_drawdown_pct
        and f.test_trades >= min_trades_per_fold
    ]
    reasons: list[str] = []
    if len(passed) / len(folds) < min_pass_ratio:
        reasons.append("INSUFFICIENT_OUT_OF_SAMPLE_FOLDS")
    if mean(f.test_expectancy for f in folds) <= min_expectancy:
        reasons.append("NEGATIVE_MEAN_EXPECTANCY")
    if mean(f.test_profit_factor for f in folds) < min_profit_factor:
        reasons.append("WEAK_MEAN_PROFIT_FACTOR")
    return PromotionDecision(not reasons, tuple(reasons), len(passed), len(folds))
