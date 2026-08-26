"""Bounded multi-asset public-feed paper session."""
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


def run_multi_asset_paper_session(*, feed, loop: PaperExecutionLoop, duration_seconds: int = 3600,
    interval_seconds: int = 30, universe: tuple[str, ...] = DEFAULT_LIQUID_UNIVERSE,
    sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> MultiAssetPaperResult:
    if duration_seconds <= 0 or interval_seconds <= 0:
        raise ValueError("duration_seconds and interval_seconds must be positive")
    symbols = tuple(dict.fromkeys(str(s).upper() for s in universe if s))
    if not symbols:
        raise ValueError("universe must not be empty")

    started = clock(); cycles = successful = errors = 0
    selected: list[str] = []
    history = {s: deque(maxlen=6) for s in symbols}
    failure_streak = {s: 0 for s in symbols}
    quarantined: set[str] = set()

    while clock() - started < duration_seconds:
        cycles += 1; snapshots: list[AssetSnapshot] = []
        position = loop.account.position
        if position is not None:
            try:
                snap = feed.snapshot(position.symbol)
                loop.on_market({"symbol": snap.symbol, "price": snap.price, "direction": position.direction,
                                "stop_distance": max(snap.price * 0.0075, 1e-8), "timestamp": snap.timestamp})
                successful += 1
            except Exception:
                errors += 1
            if loop.account.position is not None:
                remaining = duration_seconds - (clock() - started)
                if remaining > 0: sleep(min(interval_seconds, remaining))
                continue

        for symbol in symbols:
            if symbol in quarantined:
                continue
            try:
                snap = feed.snapshot(symbol); price = float(snap.price)
                failure_streak[symbol] = 0
                prices = history[symbol]; prices.append(price)
                change_pct = ((price / prices[0]) - 1.0) * 100.0 if len(prices) >= 3 else 0.0
                moves = [abs((prices[i] / prices[i-1] - 1.0) * 100.0) for i in range(1, len(prices))]
                snapshots.append(AssetSnapshot(symbol, price, float(getattr(snap, "quote_volume", 0.0)),
                                               change_pct, max(moves, default=0.0)))
                successful += 1
            except Exception:
                errors += 1; failure_streak[symbol] += 1
                # Do not waste every scan on a product absent from all providers.
                if failure_streak[symbol] >= 3:
                    quarantined.add(symbol)

        ranked = rank_assets(snapshots, min_quote_volume=2_000_000.0, max_candidates=10)
        # Evaluate the ranked set, not only the most liquid coin. Long entries
        # require positive momentum; falling coins are never entered as LONG.
        for candidate in ranked:
            live = next(s for s in snapshots if s.symbol == candidate.symbol)
            if live.change_pct >= 0.12 and live.volatility_pct >= 0.05:
                if candidate.symbol not in selected:
                    selected.append(candidate.symbol)
                loop.on_market({"symbol": candidate.symbol, "price": live.price, "direction": "LONG",
                                "stop_distance": max(live.price * 0.0075, 1e-8), "timestamp": None})
                break

        remaining = duration_seconds - (clock() - started)
        if remaining <= 0: break
        sleep(min(interval_seconds, remaining))

    return MultiAssetPaperResult(duration_seconds // 60, len(symbols), cycles, successful, errors,
                                 tuple(selected), loop.summary(mark_price=None))
