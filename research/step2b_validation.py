"""Step 2b validation helpers.

Validation is deliberately separate from parameter optimization. Every candidate
strategy is evaluated on the same validated, chronological candle set and the
same multi-position portfolio/risk assumptions.
"""
from __future__ import annotations

from collections import Counter
from typing import Callable, Iterable, Mapping

from multi_position_backtest import MultiPositionBacktester

Strategy = Callable[[dict], Mapping | None]
REQUIRED = ("timestamp", "symbol", "close")


def validate_candles(candles: Iterable[dict]) -> list[dict]:
    rows = [dict(row) for row in candles]
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    previous: str | None = None
    for i, row in enumerate(rows):
        missing = [key for key in REQUIRED if key not in row]
        if missing:
            errors.append(f"row {i}: missing {','.join(missing)}")
            continue
        timestamp = str(row["timestamp"])
        symbol = str(row["symbol"]).upper()
        if previous is not None and timestamp < previous:
            errors.append(f"row {i}: timestamps are not chronological")
        previous = timestamp
        key = (timestamp, symbol)
        if key in seen:
            errors.append(f"row {i}: duplicate timestamp/symbol {key}")
        seen.add(key)
        try:
            close = float(row["close"])
            high = float(row.get("high", close))
            low = float(row.get("low", close))
            if close <= 0 or low <= 0 or high <= 0 or not low <= close <= high:
                errors.append(f"row {i}: invalid OHLC")
        except (TypeError, ValueError):
            errors.append(f"row {i}: non-numeric OHLC")
    if errors:
        raise ValueError("invalid historical dataset: " + "; ".join(errors[:10]))
    return rows


def dataset_diagnostics(candles: Iterable[dict]) -> dict:
    rows = validate_candles(candles)
    symbols = Counter(str(row["symbol"]).upper() for row in rows)
    timestamps = [str(row["timestamp"]) for row in rows]
    return {"rows": len(rows), "symbols": dict(symbols), "unique_symbols": len(symbols),
            "start": min(timestamps) if timestamps else None, "end": max(timestamps) if timestamps else None}


def benchmark_multi_position(candles: Iterable[dict], strategies: Mapping[str, Strategy], *,
                              capital=1000.0, risk_pct=0.5, fee_pct=0.1,
                              slippage_pct=0.02, max_daily_loss_pct=3.0) -> dict[str, dict]:
    rows = validate_candles(candles)
    config = dict(capital=capital, risk_pct=risk_pct, fee_pct=fee_pct,
                  slippage_pct=slippage_pct, max_daily_loss_pct=max_daily_loss_pct)
    results: dict[str, dict] = {}
    for name, strategy in strategies.items():
        result = MultiPositionBacktester(**config).run(rows, strategy)
        summary = result.summary()
        summary["dataset_rows"] = len(rows)
        summary["dataset_symbols"] = len({str(r["symbol"]).upper() for r in rows})
        results[name] = summary
    return results
