"""Phase 4 robustness analysis primitives.

Dependency-light Monte Carlo helpers for stress-testing a sequence of trade
returns. The engine never changes the supplied trade data; it resamples the
observed returns and reports the distribution of terminal equity and maximum
drawdown.
"""

from math import isfinite
import random


def _clean_returns(trade_returns):
    values = []
    for value in trade_returns:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if isfinite(number):
            values.append(number)
    return values


def max_drawdown(equity_curve):
    """Return maximum percentage drawdown from an equity sequence."""
    if not equity_curve:
        return 0.0
    peak = float(equity_curve[0])
    worst = 0.0
    for equity in equity_curve[1:]:
        equity = float(equity)
        if equity > peak:
            peak = equity
        if peak > 0:
            drawdown = (equity / peak - 1.0) * 100.0
            worst = min(worst, drawdown)
    return worst


def _percentile(values, percentile):
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile / 100.0
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def monte_carlo(trade_returns, simulations=2000, seed=42, initial_equity=100.0):
    """Bootstrap trade returns and return deterministic robustness statistics."""
    returns = _clean_returns(trade_returns)
    simulations = int(simulations)
    initial_equity = float(initial_equity)

    if len(returns) < 10:
        return {
            "status": "INSUFFICIENT_TRADES",
            "trades": len(returns),
            "simulations": 0,
            "probability_profit": 0.0,
            "terminal_return_p05": 0.0,
            "terminal_return_p50": 0.0,
            "terminal_return_p95": 0.0,
            "max_drawdown_p95": 0.0,
        }
    if simulations <= 0 or initial_equity <= 0:
        raise ValueError("simulations and initial_equity must be positive")

    rng = random.Random(seed)
    terminal_returns = []
    drawdowns = []

    for _ in range(simulations):
        equity = initial_equity
        curve = [equity]
        for _trade in returns:
            sampled = rng.choice(returns)
            equity *= 1.0 + sampled / 100.0
            equity = max(equity, 0.0)
            curve.append(equity)
        terminal_returns.append((equity / initial_equity - 1.0) * 100.0)
        drawdowns.append(max_drawdown(curve))

    profitable = sum(1 for value in terminal_returns if value > 0)
    probability_profit = profitable / simulations
    return {
        "status": "OK",
        "trades": len(returns),
        "simulations": simulations,
        "probability_profit": round(probability_profit, 6),
        "terminal_return_p05": round(_percentile(terminal_returns, 5), 4),
        "terminal_return_p50": round(_percentile(terminal_returns, 50), 4),
        "terminal_return_p95": round(_percentile(terminal_returns, 95), 4),
        "max_drawdown_p95": round(_percentile(drawdowns, 95), 4),
    }


def robustness_score(result):
    """Map Monte Carlo output to a conservative 0-100 robustness score."""
    if result.get("status") != "OK":
        return 0.0

    profit = min(max(float(result.get("probability_profit", 0.0)), 0.0), 1.0)
    p05 = float(result.get("terminal_return_p05", 0.0))
    dd95 = abs(float(result.get("max_drawdown_p95", 0.0)))

    profit_component = profit * 50.0
    downside_component = min(max((p05 + 20.0) / 40.0, 0.0), 1.0) * 30.0
    drawdown_component = min(max((30.0 - dd95) / 30.0, 0.0), 1.0) * 20.0

    return round(profit_component + downside_component + drawdown_component, 4)
