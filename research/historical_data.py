"""Deterministic public Binance historical candle downloader."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests

BASE_URL = "https://data-api.binance.vision/api/v3/klines"
INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}


def _timestamp_ms(value: str | int | float) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _row(raw: list) -> dict:
    return {
        "timestamp": int(raw[0]),
        "open": float(raw[1]),
        "high": float(raw[2]),
        "low": float(raw[3]),
        "close": float(raw[4]),
        "volume": float(raw[5]),
        "close_timestamp": int(raw[6]),
        "quote_volume": float(raw[7]),
        "trades": int(raw[8]),
    }


def fetch_klines(symbol: str, interval: str, start: str | int, end: str | int, *, session=None, timeout: int = 30, pause_seconds: float = 0.05) -> list[dict]:
    """Fetch a complete [start,end) candle range using paginated public REST calls."""
    symbol = str(symbol).upper().strip()
    if interval not in INTERVAL_MS:
        raise ValueError(f"Unsupported interval: {interval}")
    start_ms, end_ms = _timestamp_ms(start), _timestamp_ms(end)
    if start_ms >= end_ms:
        raise ValueError("start must be before end")
    client = session or requests.Session()
    cursor = start_ms
    result: list[dict] = []
    step = INTERVAL_MS[interval]
    while cursor < end_ms:
        response = client.get(BASE_URL, params={"symbol": symbol, "interval": interval, "startTime": cursor, "endTime": end_ms - 1, "limit": 1000}, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError(f"Unexpected Binance response for {symbol}: {payload!r}")
        if not payload:
            break
        for raw in payload:
            if not isinstance(raw, list) or len(raw) < 9:
                raise RuntimeError(f"Malformed Binance candle for {symbol}: {raw!r}")
            candle = _row(raw)
            if start_ms <= candle["timestamp"] < end_ms:
                result.append(candle)
        last_open = int(payload[-1][0])
        next_cursor = last_open + step
        if next_cursor <= cursor:
            raise RuntimeError(f"Binance pagination stalled for {symbol} at {cursor}")
        cursor = next_cursor
        if len(payload) < 1000:
            break
        if pause_seconds:
            time.sleep(pause_seconds)
    result.sort(key=lambda item: item["timestamp"])
    deduped = {item["timestamp"]: item for item in result}
    return [deduped[key] for key in sorted(deduped)]


def save_jsonl(rows: Iterable[dict], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")
