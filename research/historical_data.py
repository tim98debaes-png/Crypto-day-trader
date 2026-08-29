"""Historical OHLCV ingestion for Step 2b research.

Uses the public Binance spot klines endpoint. The downloader is deliberately
separate from strategy code and writes normalized JSONL so CI/research runs do
not depend on live API calls after data has been captured.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable

import requests

BASE_URL = "https://api.binance.com/api/v3/klines"
INTERVAL_MS = {"1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000, "1h": 3_600_000}


def _ms(value: str | int) -> int:
    if isinstance(value, int):
        return value
    return int(__import__("datetime").datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def fetch_klines(symbol: str, interval: str = "5m", start: str | int | None = None,
                 end: str | int | None = None, session: requests.Session | None = None) -> list[dict]:
    if interval not in INTERVAL_MS:
        raise ValueError(f"unsupported interval: {interval}")
    client = session or requests.Session()
    start_ms = _ms(start) if start is not None else None
    end_ms = _ms(end) if end is not None else None
    rows: list[dict] = []
    while True:
        params = {"symbol": symbol.upper(), "interval": interval, "limit": 1000}
        if start_ms is not None: params["startTime"] = start_ms
        if end_ms is not None: params["endTime"] = end_ms
        response = client.get(BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        for item in batch:
            rows.append({"timestamp": int(item[0]), "symbol": symbol.upper(), "open": float(item[1]), "high": float(item[2]), "low": float(item[3]), "close": float(item[4]), "volume": float(item[5])})
        if len(batch) < 1000:
            break
        next_start = int(batch[-1][0]) + INTERVAL_MS[interval]
        if start_ms is not None and next_start <= start_ms:
            raise RuntimeError("historical API pagination did not advance")
        start_ms = next_start
        if end_ms is not None and start_ms > end_ms:
            break
        time.sleep(0.1)
    return rows


def normalize(rows: Iterable[dict]) -> list[dict]:
    result = sorted((dict(row) for row in rows), key=lambda r: (int(r["timestamp"]), str(r["symbol"])))
    seen: set[tuple[int, str]] = set()
    previous: int | None = None
    for row in result:
        ts = int(row["timestamp"]); symbol = str(row["symbol"]).upper()
        key = (ts, symbol)
        if key in seen: raise ValueError(f"duplicate candle: {key}")
        seen.add(key)
        if previous is not None and ts < previous: raise ValueError("timestamps are not chronological")
        previous = ts
        o,h,l,c = map(float, (row["open"],row["high"],row["low"],row["close"]))
        if min(o,h,l,c) <= 0 or not l <= min(o,c) <= max(o,c) <= h: raise ValueError(f"invalid OHLC: {key}")
    return result


def save_jsonl(rows: Iterable[dict], path: str | Path) -> None:
    data = normalize(rows)
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for row in data: handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    tmp.replace(target)
