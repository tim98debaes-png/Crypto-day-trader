from __future__ import annotations

import argparse
from pathlib import Path

from historical_data import fetch_klines, save_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Download historical OHLCV for research")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", default="data/historical")
    args = parser.parse_args()
    for symbol in args.symbols:
        rows = fetch_klines(symbol, args.interval, args.start, args.end)
        path = Path(args.output) / args.interval / f"{symbol.upper()}.jsonl"
        save_jsonl(rows, path)
        print(f"{symbol.upper()}: {len(rows)} candles -> {path}")


if __name__ == "__main__":
    main()
