"""Reproducible Step 2b runner.

Downloads the exact scanner research universe, validates historical candles,
and produces a deterministic manifest. Strategy execution is intentionally
separated so no result can be reported until A/B/C adapters are present.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from multi_asset_scanner import liquid_universe
from historical_data import fetch_klines, save_jsonl


def build_manifest(symbols: list[str], interval: str, start: str, end: str, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbols": symbols,
        "interval": interval,
        "start": start,
        "end": end,
        "files": [],
        "strategies": ["A_LEGACY", "B_CURRENT", "C_HYBRID"],
        "status": "DATASET_READY_AWAITING_STRATEGY_ADAPTERS",
    }
    for symbol in symbols:
        rows = fetch_klines(symbol, interval, start, end)
        path = output / interval / f"{symbol}.jsonl"
        save_jsonl(rows, path)
        manifest["files"].append({"symbol": symbol, "path": str(path), "candles": len(rows)})
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--max-assets", type=int, default=50)
    parser.add_argument("--output", default="data/historical")
    args = parser.parse_args()
    symbols = list(liquid_universe(max_assets=args.max_assets))
    manifest = build_manifest(symbols, args.interval, args.start, args.end, Path(args.output))
    print(json.dumps({"status": manifest["status"], "symbols": len(symbols), "files": len(manifest["files"])}, indent=2))


if __name__ == "__main__":
    main()
