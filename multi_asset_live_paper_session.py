"""Bounded multi-asset public-feed paper session.

Scans the curated universe, uses real feed volume when available, and only
enters when a candidate has enough short-term momentum/volatility to represent
a plausible day-trading setup. No authenticated exchange client or live order
path is used.
"""
from __future__ import annotations

import time
from collections import deque
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
    *, feed, loop: PaperExecutionLoop, duration_seconds: int = 3600,
    interval_seconds: int = 30, universe: tuple[str, ...] = DEFAULT_LIQUID_UNIVERSE,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> MultiAssetPaperResult:
    if duration_seconds <= 0 or interval_seconds <= 0:
        raise ValueError("duration_seconds and interval_seconds must be positive")
    symbols = tuple(dict.fromkeys(str(symbol).upper() for symbol in universe if symbol))
    if not symbols:
        raise ValueError("universe must not be empty")

    started = clock(); cycles = successful = errors = 0
    selected: list[str] = []
    history: dict[str, deque[float]] = {s: deque(maxlen=6) for s in symbols}

    while clock() - started < duration_seconds:
        cycles += 1
        snapshots: list[AssetSnapshot] = []

        position = loop.account.position
        if position is not None:
            try:
                snap = feed.snapshot(position.symbol)
                loop.on_market({"symbol": snap.symbol, "price": snap.price,
                                "direction": position.direction,
                                "stop_distance": max(snap.price * 0.0075, 1e-8),
                                "timestamp": snap.timestamp})
                successful += 1
            except Exception:
                errors += 1
            if loop.account.position is not None:
                remaining = duration_seconds - (clock() - started)
                if remaining > 0: sleep(min(interval_seconds, remaining))
                continue

        for symbol in symbols:
            try:
                snap = feed.snapshot(symbol)
                price = float(snap.price)
                prices = history[symbol]
                prices.append(price)
                change_pct = ((price / prices[0]) - 1.0) * 100.0 if len(prices) >= 3 else 0.0
                step_moves = [abs((prices[i] / prices[i-1] - 1.0) * 100.0) for i in range(1, len(prices))]
                vol_pct = max(step_moves, default=0.0)
                snapshots.append(AssetSnapshot(
                    symbol=symbol, price=price,
                    quote_volume=float(getattr(snap, "quote_volume", 0.0)),
                    change_pct=change_pct, volatility_pct=vol_pct,
                ))
                successful += 1
            except Exception:
                errors += 1

        ranked = rank_assets(snapshots, min_quote_volume=2_000_000.0, max_candidates=5)
        if ranked:
            top = ranked[0]
            live = next(s for s in snapshots if s.symbol == top.symbol)
            # Do not trade noise: require a measurable 2.5-minute move and
            # at least 0.08% short-term movement. These are intentionally modest
            # gates, but they prevent zero-information entries.
            if abs(live.change_pct) >= 0.20 and live.volatility_pct >= 0.08:
                if top.symbol not in selected:
                    selected.append(top.symbol)
                loop.on_market({"symbol": top.symbol, "price": live.price,
                                "direction": "LONG",
                                "stop_distance": max(live.price * 0.0075, 1e-8),
                                "timestamp": None})

        remaining = duration_seconds - (clock() - started)
        if remaining <= 0: break
        sleep(min(interval_seconds, remaining))

    return MultiAssetPaperResult(
        duration_minutes=duration_seconds // 60, universe_size=len(symbols),
        scan_cycles=cycles, successful_snapshots=successful, feed_errors=errors,
        candidate_symbols=tuple(selected),
        summary=loop.summary(mark_price=None),
    )
