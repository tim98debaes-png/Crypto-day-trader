"""Reproducible A/B strategy evaluation helpers.

The harness deliberately does not optimize parameters. It evaluates named
candidate strategies on identical ordered data and cost assumptions, which is
the first step toward preventing strategy changes from being justified by
single short paper runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from backtest_engine import HistoricalBacktester

Strategy = Callable[[dict], Mapping | None]


@dataclass(frozen=True)
class BenchmarkConfig:
    capital: float = 1000.0
    risk_pct: float = 0.5
    fee_pct: float = 0.1
    slippage_pct: float = 0.02
    max_daily_loss_pct: float = 3.0


def evaluate_strategies(candles: Iterable[dict], strategies: Mapping[str, Strategy], config: BenchmarkConfig | None = None) -> dict[str, dict]:
    rows = [dict(candle) for candle in candles]
    cfg = config or BenchmarkConfig()
    results: dict[str, dict] = {}
    for name, strategy in strategies.items():
        result = HistoricalBacktester(
            capital=cfg.capital,
            risk_pct=cfg.risk_pct,
            fee_pct=cfg.fee_pct,
            slippage_pct=cfg.slippage_pct,
            max_daily_loss_pct=cfg.max_daily_loss_pct,
        ).run(rows, strategy)
        results[name] = result.summary()
    return results


def rank_results(results: Mapping[str, Mapping]) -> list[tuple[str, float, int]]:
    """Rank by profit factor only when sample size is meaningful.

    With fewer than 30 closed trades, profit factor is returned as a diagnostic
    but is not treated as evidence of a production edge. This avoids repeating
    the mistake of treating two winning trades as a validated strategy.
    """
    ranked = []
    for name, row in results.items():
        trades = int(row.get("closed_trades", 0))
        pf = float(row.get("profit_factor", 0.0))
        score = pf if trades >= 30 else float("nan")
        ranked.append((name, score, trades))
    return sorted(ranked, key=lambda item: (-(item[1] if item[1] == item[1] else float("-inf")), -item[2], item[0]))
