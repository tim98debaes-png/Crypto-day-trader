"""Bounded multi-asset public-feed paper session."""
from __future__ import annotations
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable
from multi_asset_scanner import AssetSnapshot, DEFAULT_LIQUID_UNIVERSE, RESEARCH_MIN_QUOTE_VOLUME, rank_assets
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
    diagnostics: dict


def run_multi_asset_paper_session(
    *, feed, loop: PaperExecutionLoop, duration_seconds: int = 3600,
    interval_seconds: int = 30, universe: tuple[str, ...] = DEFAULT_LIQUID_UNIVERSE,
    sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
) -> MultiAssetPaperResult:
    if duration_seconds <= 0 or interval_seconds <= 0:
        raise ValueError("duration_seconds and interval_seconds must be positive")
    symbols = tuple(dict.fromkeys(str(s).upper() for s in universe if s))
    if not symbols:
        raise ValueError("universe must not be empty")

    started = clock()
    cycles = successful = errors = 0
    selected: list[str] = []
    history = {s: deque(maxlen=6) for s in symbols}
    failure_streak = {s: 0 for s in symbols}
    quarantined: set[str] = set()

    diagnostics = {
        "assets_attempted": 0,
        "liquidity_rejections": 0,
        "ranked_candidates": 0,
        "entry_momentum_rejections": 0,
        "entry_volatility_rejections": 0,
        "entry_ready": 0,
        "opened_trades": 0,
        "closed_trades": 0,
        "peak_open_positions": 0,
        "research_gate_rejections": 0,
        "quarantined_symbols": [],
    }

    while clock() - started < duration_seconds:
        cycles += 1
        snapshots: list[AssetSnapshot] = []
        diagnostics["assets_attempted"] += len(symbols) - len(quarantined)

        # Always manage every currently open symbol. Do not use the legacy
        # account.position compatibility view, which would serialize the
        # portfolio to one position and skip the scanner while any position
        # exists.
        open_symbols = tuple(loop.account.positions.keys())
        for symbol in open_symbols:
            try:
                snap = feed.snapshot(symbol)
                loop.on_market({
                    "symbol": snap.symbol,
                    "price": snap.price,
                    "direction": loop.account.positions[symbol].direction,
                    "stop_distance": max(snap.price * 0.0075, 1e-8),
                    "timestamp": snap.timestamp,
                })
                successful += 1
            except Exception:
                errors += 1

        for symbol in symbols:
            if symbol in quarantined:
                continue
            try:
                snap = feed.snapshot(symbol)
                price = float(snap.price)
                failure_streak[symbol] = 0
                prices = history[symbol]
                prices.append(price)
                change_pct = ((price / prices[0]) - 1.0) * 100.0 if len(prices) >= 3 else 0.0
                moves = [abs((prices[i] / prices[i - 1] - 1.0) * 100.0) for i in range(1, len(prices))]
                snapshots.append(AssetSnapshot(
                    symbol, price, float(getattr(snap, "quote_volume", 0.0)),
                    change_pct, max(moves, default=0.0),
                ))
                successful += 1
            except Exception:
                errors += 1
                failure_streak[symbol] += 1
                if failure_streak[symbol] >= 3:
                    quarantined.add(symbol)

        diagnostics["liquidity_rejections"] += sum(
            1 for item in snapshots if item.price <= 0 or item.quote_volume < RESEARCH_MIN_QUOTE_VOLUME
        )
        ranked = rank_assets(
            snapshots,
            min_quote_volume=RESEARCH_MIN_QUOTE_VOLUME,
            max_candidates=10,
        )
        diagnostics["ranked_candidates"] += len(ranked)

        entry_ready = []
        for candidate in ranked:
            live = next(s for s in snapshots if s.symbol == candidate.symbol)
            if live.change_pct < 0.12:
                diagnostics["entry_momentum_rejections"] += 1
                continue
            if live.volatility_pct < 0.05:
                diagnostics["entry_volatility_rejections"] += 1
                continue
            entry_ready.append(live)

        diagnostics["entry_ready"] += len(entry_ready)

        # Evaluate all qualifying symbols. PaperAccount enforces one position
        # per symbol but intentionally has no portfolio-wide position cap.
        for live in entry_ready:
            if live.symbol in loop.account.positions:
                continue
            if live.symbol not in selected:
                selected.append(live.symbol)
            result = loop.on_market({
                "symbol": live.symbol,
                "price": live.price,
                "direction": "LONG",
                "stop_distance": max(live.price * 0.0075, 1e-8),
                "timestamp": None,
            })
            if result.get("action") == "OPEN":
                diagnostics["opened_trades"] += 1
            elif result.get("reason") in {"candidate_direction_mismatch", "paper_monitor_blocked", "paper_monitor_rollback_recovery"}:
                diagnostics["research_gate_rejections"] += 1

        diagnostics["closed_trades"] = loop.stats.closed_trades
        diagnostics["peak_open_positions"] = max(
            diagnostics["peak_open_positions"], len(loop.account.positions)
        )
        diagnostics["quarantined_symbols"] = sorted(quarantined)

        remaining = duration_seconds - (clock() - started)
        if remaining <= 0:
            break
        sleep(min(interval_seconds, remaining))

    return MultiAssetPaperResult(
        duration_seconds // 60,
        len(symbols),
        cycles,
        successful,
        errors,
        tuple(selected),
        loop.summary(mark_price=None),
        diagnostics,
    )
