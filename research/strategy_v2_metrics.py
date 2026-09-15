"""Robust performance metrics for Strategy V2 paper-parity replays.

Inspired by the multi-metric reporting used by established trading research
frameworks. This module does not optimize parameters; it only evaluates a
completed replay and therefore cannot change trading decisions.
"""
from __future__ import annotations

from math import exp, isfinite, log, sqrt
from statistics import mean, pstdev
from typing import Iterable, Mapping, Sequence


def _finite(values: Iterable[float]) -> list[float]:
    return [float(v) for v in values if isfinite(float(v))]


def _returns(equity_curve: Sequence[float]) -> list[float]:
    values = _finite(equity_curve)
    return [b / a - 1.0 for a, b in zip(values, values[1:]) if a > 0 and b > 0]


def max_drawdown_pct(equity_curve: Sequence[float]) -> float:
    values = _finite(equity_curve)
    if not values:
        return 0.0
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return abs(worst) * 100.0


def sharpe_ratio(equity_curve: Sequence[float], periods_per_year: int = 365 * 24 * 60) -> float:
    returns = _returns(equity_curve)
    if len(returns) < 2:
        return 0.0
    sigma = pstdev(returns)
    if sigma <= 0:
        return 0.0
    return mean(returns) / sigma * sqrt(periods_per_year)


def sortino_ratio(equity_curve: Sequence[float], periods_per_year: int = 365 * 24 * 60) -> float:
    returns = _returns(equity_curve)
    downside = [min(r, 0.0) for r in returns]
    downside_deviation = sqrt(mean(r * r for r in downside)) if downside else 0.0
    if downside_deviation <= 0:
        return 0.0
    return mean(returns) / downside_deviation * sqrt(periods_per_year)


def calmar_ratio(equity_curve: Sequence[float], periods_per_year: int = 365 * 24 * 60) -> float:
    values = _finite(equity_curve)
    if len(values) < 2 or values[0] <= 0:
        return 0.0
    periods = len(values) - 1
    dd = max_drawdown_pct(values) / 100.0
    if dd <= 0:
        return 0.0

    # Log-space annualisation prevents OverflowError on very short synthetic
    # curves while keeping the metric deterministic and finite.
    growth = values[-1] / values[0]
    if growth <= 0:
        return 0.0
    exponent = log(growth) * (periods_per_year / periods)
    annualized_return = exp(min(exponent, 700.0)) - 1.0
    return annualized_return / dd


def trade_metrics(audit_log: Sequence[Mapping[str, object]]) -> dict[str, float | int]:
    closes = [event for event in audit_log if event.get("event") == "CLOSE"]
    pnls = [float(event.get("pnl", 0.0)) for event in closes]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    streak = max_streak = 0
    for pnl in pnls:
        if pnl < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    expectancy = sum(pnls) / len(pnls) if pnls else 0.0
    payoff = (mean(wins) / abs(mean(losses))) if wins and losses else 0.0
    return {
        "closed_trades": len(pnls),
        "expectancy_per_trade": expectancy,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "payoff_ratio": payoff,
        "max_consecutive_losses": max_streak,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else 0.0,
    }


def build_metrics(equity_curve: Sequence[float], audit_log: Sequence[Mapping[str, object]]) -> dict[str, float | int]:
    return {
        "max_drawdown_pct": max_drawdown_pct(equity_curve),
        "sharpe_ratio": sharpe_ratio(equity_curve),
        "sortino_ratio": sortino_ratio(equity_curve),
        "calmar_ratio": calmar_ratio(equity_curve),
        **trade_metrics(audit_log),
    }
