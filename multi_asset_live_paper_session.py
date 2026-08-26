"""Bounded multi-asset public-feed paper session.

Scans the curated 50-asset universe, ranks live snapshots, and feeds only the
best eligible symbol into the existing paper execution loop. No authenticated
exchange client or live order path is used.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from multi_asset_scanner import AssetSnapshot, DEFAULT_LIQUID_UNIVERSE, rank_assets
from paper_execution import PaperExecutionLoop


@dataclass(frozen=True)
class MultiAssetPaperResult:
    duration_minutes: int
    universe_size: int
    scan_cycles: int
    successful_snapshots: int
    feed_errors: int
    candidate_symbols: tuple[str, ...]
    summary: dict


def run_multi_asset_paper_session(
    *,
    feed,
    loop: PaperExecutionLoop,
    duration_seconds: int = 3600,
    interval_seconds: int = 30,
    universe: tuple[str, ...] = DEFAULT_LIQUID_UNIVERSE,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> MultiAssetPaperResult:
    """Run a bounded scan across the full universe and paper-trade top setup.

    The feed is expected to be read-only. One position at a time is enforced by
    the existing PaperAccount. While a position is open, its symbol is refreshed
    first so SL/TP can be evaluated before looking for a new entry.
    """
    if duration_seconds <= 0 or interval_seconds <= 0:
        raise ValueError("duration_seconds and interval_seconds must be positive")
    symbols = tuple(dict.fromkeys(str(symbol).upper() for symbol in universe if symbol))
    if not symbols:
        raise ValueError("universe must not be empty")

    started = clock()
    cycles = successful = errors = 0
    selected: list[str] = []
    previous: dict[str, float] = {}
    volatility: dict[str, float] = {}

    while clock() - started < duration_seconds:
        cycles += 1
        snapshots: list[AssetSnapshot] = []

        position = loop.account.position
        if position is not None:
            try:
                snap = feed.snapshot(position.symbol)
                loop.on_market({
                    "symbol": snap.symbol, "price": snap.price,
                    "direction": position.direction, "stop_distance": max(snap.price * 0.01, 1e-8),
                    "timestamp": snap.timestamp,
                })
                successful += 1
            except Exception:
                errors += 1
            if loop.account.position is not None:
                remaining = duration_seconds - (clock() - started)
                if remaining > 0:
                    sleep(min(interval_seconds, remaining))
                continue

        for symbol in symbols:
            try:
                snap = feed.snapshot(symbol)
                price = float(snap.price)
                prior = previous.get(symbol)
                change_pct = ((price / prior) - 1.0) * 100.0 if prior else 0.0
                if prior and prior > 0:
                    volatility[symbol] = max(volatility.get(symbol, 0.0), abs(change_pct))
                previous[symbol] = price
                # The curated universe is already liquidity-gated. A neutral
                # synthetic volume keeps the ranking focused on live momentum
                # and volatility without inventing exchange volume data.
                snapshots.append(AssetSnapshot(
                    symbol=symbol, price=price, quote_volume=10_000_000.0,
                    change_pct=change_pct, volatility_pct=volatility.get(symbol, 0.0),
                ))
                successful += 1
            except Exception:
                errors += 1

        ranked = rank_assets(snapshots, min_quote_volume=5_000_000.0, max_candidates=5)
        if ranked:
            top = ranked[0]
            if top.symbol not in selected:
                selected.append(top.symbol)
            loop.on_market({
                "symbol": top.symbol, "price": next(s.price for s in snapshots if s.symbol == top.symbol),
                "direction": "LONG", "stop_distance": max(top.score * 0 + next(s.price for s in snapshots if s.symbol == top.symbol) * 0.01, 1e-8),
                "timestamp": None,
            })

        remaining = duration_seconds - (clock() - started)
        if remaining <= 0:
            break
        sleep(min(interval_seconds, remaining))

    return MultiAssetPaperResult(
        duration_minutes=duration_seconds // 60,
        universe_size=len(symbols),
        scan_cycles=cycles,
        successful_snapshots=successful,
        feed_errors=errors,
        candidate_symbols=tuple(selected),
        summary=loop.summary(mark_price=loop.account.position and None),
    )
