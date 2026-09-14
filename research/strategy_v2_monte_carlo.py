"""Monte Carlo robustness tests for Strategy V2.

The simulation deliberately separates two questions:
1. trade-order sensitivity: same trades, shuffled order;
2. outcome uncertainty: bootstrap trades with replacement.

Neither simulation feeds results back into trading decisions.
"""
from __future__ import annotations

import random
from statistics import median
from typing import Mapping, Sequence


def _path_stats(pnls: Sequence[float], initial_capital: float) -> tuple[float, float]:
    equity = initial_capital
    peak = equity
    max_dd = 0.0
    for pnl in pnls:
        equity += float(pnl)
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
    return equity, max_dd


def _percentile(values: Sequence[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * p))))]


def _trade_pnls(audit_log: Sequence[Mapping[str, object]]) -> list[float]:
    return [float(e["pnl"]) for e in audit_log if e.get("event") == "CLOSE" and "pnl" in e]


def trade_order_monte_carlo(
    audit_log: Sequence[Mapping[str, object]],
    *,
    initial_capital: float = 1000.0,
    simulations: int = 500,
    seed: int = 42,
) -> dict[str, float | int]:
    """Shuffle the observed trades to measure path/order sensitivity."""
    if initial_capital <= 0 or simulations < 1:
        raise ValueError("initial_capital must be positive and simulations must be >= 1")
    pnls = _trade_pnls(audit_log)
    if not pnls:
        return {
            "simulations": 0,
            "trades": 0,
            "median_final_equity": initial_capital,
            "p05_final_equity": initial_capital,
            "p95_final_equity": initial_capital,
            "probability_of_loss_pct": 0.0,
            "median_max_drawdown_pct": 0.0,
            "p95_max_drawdown_pct": 0.0,
            "seed": seed,
        }
    rng = random.Random(seed)
    finals: list[float] = []
    drawdowns: list[float] = []
    for _ in range(simulations):
        shuffled = list(pnls)
        rng.shuffle(shuffled)
        final, dd = _path_stats(shuffled, initial_capital)
        finals.append(final)
        drawdowns.append(dd)
    return {
        "simulations": simulations,
        "trades": len(pnls),
        "median_final_equity": median(finals),
        "p05_final_equity": _percentile(finals, 0.05),
        "p95_final_equity": _percentile(finals, 0.95),
        "probability_of_loss_pct": sum(value < initial_capital for value in finals) / len(finals) * 100.0,
        "median_max_drawdown_pct": median(drawdowns),
        "p95_max_drawdown_pct": _percentile(drawdowns, 0.95),
        "seed": seed,
    }


def bootstrap_monte_carlo(
    audit_log: Sequence[Mapping[str, object]],
    *,
    initial_capital: float = 1000.0,
    simulations: int = 500,
    seed: int = 42,
) -> dict[str, float | int]:
    """Bootstrap observed trades with replacement to model outcome uncertainty."""
    if initial_capital <= 0 or simulations < 1:
        raise ValueError("initial_capital must be positive and simulations must be >= 1")
    pnls = _trade_pnls(audit_log)
    if not pnls:
        return {
            "simulations": 0,
            "trades_per_simulation": 0,
            "median_final_equity": initial_capital,
            "p05_final_equity": initial_capital,
            "p95_final_equity": initial_capital,
            "probability_of_loss_pct": 0.0,
            "median_max_drawdown_pct": 0.0,
            "p95_max_drawdown_pct": 0.0,
            "seed": seed,
        }
    rng = random.Random(seed)
    finals: list[float] = []
    drawdowns: list[float] = []
    for _ in range(simulations):
        sampled = [pnls[rng.randrange(len(pnls))] for _ in pnls]
        final, dd = _path_stats(sampled, initial_capital)
        finals.append(final)
        drawdowns.append(dd)
    return {
        "simulations": simulations,
        "trades_per_simulation": len(pnls),
        "median_final_equity": median(finals),
        "p05_final_equity": _percentile(finals, 0.05),
        "p95_final_equity": _percentile(finals, 0.95),
        "probability_of_loss_pct": sum(value < initial_capital for value in finals) / len(finals) * 100.0,
        "median_max_drawdown_pct": median(drawdowns),
        "p95_max_drawdown_pct": _percentile(drawdowns, 0.95),
        "seed": seed,
    }
