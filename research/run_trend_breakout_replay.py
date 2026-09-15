"""Run the cost-aware trend-breakout replay on downloaded historical candles."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.historical_data import fetch_klines
from research.trend_breakout_replay import ReplayConfig, replay_ohlcv
from strategy_trend_breakout import TrendBreakoutConfig


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", default="research/results/trend_breakout_baseline.json")
    args = parser.parse_args()

    rows = fetch_klines(args.symbol, args.interval, args.start, args.end)
    if not rows:
        raise RuntimeError("No historical candles returned")

    frame = pd.DataFrame(rows)
    frame.columns = [str(c).lower() for c in frame.columns]
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"historical data missing columns: {sorted(missing)}")
    for column in required:
        frame[column] = pd.to_numeric(frame[column], errors="raise")

    result = replay_ohlcv(
        frame,
        strategy=TrendBreakoutConfig(),
        config=ReplayConfig(),
    )
    result["symbol"] = args.symbol
    result["interval"] = args.interval
    result["start"] = args.start
    result["end"] = args.end
    result["strategy"] = "Donchian20_EMA20_50_ATR14_2.5R"

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")

    summary = {k: result[k] for k in ("symbol", "interval", "start", "end", "initial_capital", "final_equity", "pnl", "closed_trades", "win_rate_pct", "profit_factor", "max_drawdown_pct")}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
