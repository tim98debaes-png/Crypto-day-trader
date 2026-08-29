"""Historical OHLCV ingestion for Step 2b research.

Uses Binance public market data. CI runners can receive HTTP 451 from the
REST API, so the downloader tries public market-data API hosts and then falls
back to Binance's official bulk historical kline archives. Strategy code
remains isolated from data acquisition.
"""
from __future__ import annotations

import csv
import io
import json
import time
import zipfile
from calendar import monthrange
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests

BASE_URLS = (
    "https://data-api.binance.vision/api/v3/klines",
    "https://api-gcp.binance.com/api/v3/klines",
    "https://api.binance.com/api/v3/klines",
)
BULK_BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"
INTERVAL_MS = {"1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000, "1h": 3_600_000}


def _ms(value: str | int) -> int:
    if isinstance(value, int):
        return value
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _bulk_months(start_ms: int, end_ms: int) -> list[tuple[int, int]]:
    start = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
    end = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc)
    year, month = start.year, start.month
    result: list[tuple[int, int]] = []
    while (year, month) <= (end.year, end.month):
        first = datetime(year, month, 1, tzinfo=timezone.utc)
        last = datetime(year, month, monthrange(year, month)[1], 23, 59, 59, 999000, tzinfo=timezone.utc)
        result.append((max(start_ms, int(first.timestamp() * 1000)), min(end_ms, int(last.timestamp() * 1000))))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return result


def _fetch_bulk(symbol: str, interval: str, start_ms: int, end_ms: int, client: requests.Session) -> list[dict]:
    rows: list[dict] = []
    for month_start, month_end in _bulk_months(start_ms, end_ms):
        month_dt = datetime.fromtimestamp(month_start / 1000, tz=timezone.utc)
        month_name = f"{month_dt.year:04d}-{month_dt.month:02d}"
        url = f"{BULK_BASE_URL}/{symbol.upper()}/{interval}/{symbol.upper()}-{interval}-{month_name}.zip"
        response = client.get(url, timeout=60)
        if response.status_code == 404:
            raise RuntimeError(f"Binance bulk archive not found: {url}")
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not members:
                raise RuntimeError(f"Binance bulk archive contains no CSV: {url}")
            with archive.open(members[0]) as handle:
                text = io.TextIOWrapper(handle, encoding="utf-8", newline="")
                reader = csv.reader(text)
                for item in reader:
                    if not item or not item[0].isdigit():
                        continue
                    ts = int(item[0])
                    if ts < start_ms or ts > end_ms:
                        continue
                    rows.append({
                        "timestamp": ts,
                        "symbol": symbol.upper(),
                        "open": float(item[1]),
                        "high": float(item[2]),
                        "low": float(item[3]),
                        "close": float(item[4]),
                        "volume": float(item[5]),
                    })
    return rows


def fetch_klines(symbol: str, interval: str = "5m", start: str | int | None = None,
                 end: str | int | None = None, session: requests.Session | None = None) -> list[dict]:
    if interval not in INTERVAL_MS:
        raise ValueError(f"unsupported interval: {interval}")
    client = session or requests.Session()
    start_ms = _ms(start) if start is not None else None
    end_ms = _ms(end) if end is not None else None
    if start_ms is None or end_ms is None:
        raise ValueError("start and end are required for reproducible historical downloads")
    if end_ms < start_ms:
        raise ValueError("end must be >= start")

    last_error: Exception | None = None
    for base_url in BASE_URLS:
        try:
            rows: list[dict] = []
            cursor = start_ms
            while cursor <= end_ms:
                params = {"symbol": symbol.upper(), "interval": interval, "limit": 1000, "startTime": cursor, "endTime": end_ms}
                response = client.get(base_url, params=params, timeout=30)
                response.raise_for_status()
                batch = response.json()
                if not batch:
                    break
                for item in batch:
                    rows.append({"timestamp": int(item[0]), "symbol": symbol.upper(), "open": float(item[1]), "high": float(item[2]), "low": float(item[3]), "close": float(item[4]), "volume": float(item[5])})
                if len(batch) < 1000:
                    break
                next_cursor = int(batch[-1][0]) + INTERVAL_MS[interval]
                if next_cursor <= cursor:
                    raise RuntimeError("historical API pagination did not advance")
                cursor = next_cursor
                time.sleep(0.05)
            return rows
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc

    try:
        return _fetch_bulk(symbol, interval, start_ms, end_ms, client)
    except Exception as bulk_error:
        raise RuntimeError(
            f"Unable to fetch {symbol} {interval} historical data. "
            f"REST sources failed with {last_error!r}; bulk archive failed with {bulk_error!r}."
        ) from bulk_error


def normalize(rows: Iterable[dict]) -> list[dict]:
    result = sorted((dict(row) for row in rows), key=lambda r: (int(r["timestamp"]), str(r["symbol"])))
    seen: set[tuple[int, str]] = set()
    previous_by_symbol: dict[str, int] = {}
    for row in result:
        ts = int(row["timestamp"]); symbol = str(row["symbol"]).upper()
        key = (ts, symbol)
        if key in seen:
            raise ValueError(f"duplicate candle: {key}")
        seen.add(key)
        previous = previous_by_symbol.get(symbol)
        if previous is not None and ts < previous:
            raise ValueError(f"timestamps are not chronological for {symbol}")
        previous_by_symbol[symbol] = ts
        o, h, l, c = map(float, (row["open"], row["high"], row["low"], row["close"]))
        if min(o, h, l, c) <= 0 or not l <= min(o, c) <= max(o, c) <= h:
            raise ValueError(f"invalid OHLC: {key}")
    return result


def save_jsonl(rows: Iterable[dict], path: str | Path) -> None:
    data = normalize(rows)
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for row in data:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    tmp.replace(target)
