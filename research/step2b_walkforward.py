"""Step 2b: leakage-safe walk-forward evaluation for strategy research."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping
from multi_position_backtest import MultiPositionBacktester

Strategy = Callable[[dict], Mapping | None]

@dataclass(frozen=True)
class WalkForwardWindow:
    train: tuple[dict, ...]
    validation: tuple[dict, ...]
    test: tuple[dict, ...]


def chronological_split(candles: Iterable[dict], train_pct: float = 0.60,
                        validation_pct: float = 0.20) -> WalkForwardWindow:
    rows = [dict(row) for row in candles]
    if not rows:
        raise ValueError("historical dataset is empty")
    if not 0 < train_pct < 1 or not 0 < validation_pct < 1 or train_pct + validation_pct >= 1:
        raise ValueError("train_pct and validation_pct must leave a positive test set")
    rows.sort(key=lambda row: str(row["timestamp"]))
    n = len(rows)
    train_end = max(1, int(n * train_pct))
    validation_end = max(train_end + 1, int(n * (train_pct + validation_pct)))
    validation_end = min(validation_end, n - 1)
    return WalkForwardWindow(tuple(rows[:train_end]), tuple(rows[train_end:validation_end]), tuple(rows[validation_end:]))


def evaluate_fixed_strategies(candles: Iterable[dict], strategies: Mapping[str, Strategy], *,
                              capital: float = 1000.0, risk_pct: float = 0.5,
                              fee_pct: float = 0.1, slippage_pct: float = 0.02,
                              max_daily_loss_pct: float = 3.0) -> dict[str, dict]:
    rows = [dict(row) for row in candles]
    window = chronological_split(rows)
    config = dict(capital=capital, risk_pct=risk_pct, fee_pct=fee_pct,
                  slippage_pct=slippage_pct, max_daily_loss_pct=max_daily_loss_pct)
    output: dict[str, dict] = {}
    for name, strategy in strategies.items():
        result = MultiPositionBacktester(**config).run(window.test, strategy)
        summary = result.summary()
        summary.update({"train_rows": len(window.train), "validation_rows": len(window.validation),
                        "test_rows": len(window.test), "test_start": window.test[0]["timestamp"],
                        "test_end": window.test[-1]["timestamp"]})
        output[name] = summary
    return output


def compare_single_position_parity(candles: Iterable[dict], strategy: Strategy, **config) -> tuple[dict, dict]:
    """Compare legacy and multi-position semantics on one symbol."""
    from backtest_engine import HistoricalBacktester
    rows = [dict(row) for row in candles]
    old = HistoricalBacktester(**config).run(rows, strategy).summary()
    new = MultiPositionBacktester(**config).run(rows, strategy).summary()
    return old, new
