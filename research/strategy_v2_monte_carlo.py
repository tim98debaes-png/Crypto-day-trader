"""Trade-order Monte Carlo robustness test for Strategy V2.

This follows the useful idea of testing whether a backtest's outcome depends
heavily on the exact order of trades. It does not optimize the strategy and
never feeds simulated results back into trading decisions.
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


def trade_order_monte_carlo(
    audit_log: Sequence[Mapping[str, object]],
    *,
    initial_capital: float = 1000.0,
    simulations: int = 500,
    seed: int = 42,
) -> dict[str, float | int]:
    if initial_capital <= 0 or simulations < 1:
        raise ValueError("initial_capital must be positive and simulations must be >= 1")
    pnls = [float(e["pnl"]) for e in audit_log if e.get("event") == "CLOSE" and "pnl" in e]
    if not pnls:
        return {"simulations": 0, "trades": 0, "median_final_equity": initial_capital, "p05_final_equity": initial_capital, "p95_final_equity": initial_capital, "probability_of_loss_pct": 0.0, "median_max_drawdown_pct": 0.0, "p95_max_drawdown_pct": 0.0}
    rng = random.Random(seed)
    finals: list[float] = []
    drawdowns: list[float] = []
    for _ in range(simulations):
        shuffled = list(pnls)
        rng.shuffle(shuffled)
        final, dd = _path_stats(shuffled, initial_capital)
        finals.append(final)
        drawdowns.append(dd)
    finals.sort()
    drawdowns.sort()
    percentile = lambda values, p: values[min(len(values) - 1, max(0, int(round((len(values) - 1) * p))))]
    return {
        "simulations": simulations,
        "trades": len(pnls),
        "median_final_equity": median(finals),
        "p05_final_equity": percentile(finals, 0.05),
        "p95_final_equity": percentile(finals, 0.95),
        "probability_of_loss_pct": sum(value < initial_capital for value in finals) / len(finals) * 100.0,
        "median_max_drawdown_pct": median(drawdowns),
        "p95_max_drawdown_pct": percentile(drawdowns, 0.95),
        "seed": seed,
    }
