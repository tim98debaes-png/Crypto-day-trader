"""Bounded multi-asset public-feed paper session with directional pullback entries."""
from __future__ import annotations
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable
from entry_exit_logic import entry_signal_details, exit_signal
from multi_asset_scanner import AssetSnapshot, DEFAULT_LIQUID_UNIVERSE, RESEARCH_MIN_QUOTE_VOLUME, rank_assets
from paper_execution import PaperExecutionLoop
from strategy_risk_controls import RISK_CONFIG, exceeds_correlation_limit, sector_position_count

TIER_A_MIN_SCORE = 5
TIER_B_MIN_SCORE = 4
TIER_B_RISK_PCT = 0.25

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

def _ema(values: list[float], period: int) -> float | None:
    if not values:
        return None
    alpha = 2.0 / (period + 1.0)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1.0 - alpha) * result
    return result

def _empty_trade_stats() -> dict:
    return {"trades": 0, "wins": 0, "losses": 0, "gross_profit": 0.0, "gross_loss": 0.0, "net_pnl": 0.0}

def _finalize_trade_stats(stats: dict) -> dict:
    result = dict(stats)
    result["win_rate_pct"] = result["wins"] / result["trades"] * 100.0 if result["trades"] else 0.0
    result["profit_factor"] = result["gross_profit"] / result["gross_loss"] if result["gross_loss"] else (float("inf") if result["gross_profit"] else 0.0)
    return result

def _audit_diagnostics(audit_log: list[dict]) -> dict:
    opens: dict[str, dict] = {}
    score_groups = {f"{x}/5": _empty_trade_stats() for x in (3, 4, 5)}
    tier_groups = {"A": _empty_trade_stats(), "B": _empty_trade_stats()}
    direction_groups = {"LONG": _empty_trade_stats(), "SHORT": _empty_trade_stats()}
    coin_groups: dict[str, dict] = {}
    exit_groups: dict[str, dict] = {}
    execution: list[dict] = []
    for event in audit_log:
        symbol = str(event.get("symbol", ""))
        kind = str(event.get("event", "")).upper()
        if kind == "OPEN":
            opens[symbol] = event
            continue
        if kind != "CLOSE":
            continue
        opened = opens.pop(symbol, {})
        pnl = float(event.get("pnl", 0.0))
        score = event.get("strategy_score", opened.get("strategy_score"))
        tier = event.get("strategy_tier", opened.get("strategy_tier"))
        direction = str(event.get("direction", opened.get("direction", "UNKNOWN"))).upper()
        reason = str(event.get("reason", "UNKNOWN"))
        groups: list[dict] = []
        if score is not None and int(score) in (3, 4, 5):
            groups.append(score_groups[f"{int(score)}/5"])
        if tier in tier_groups:
            groups.append(tier_groups[tier])
        direction_groups.setdefault(direction, _empty_trade_stats())
        groups.append(direction_groups[direction])
        coin_groups.setdefault(symbol, _empty_trade_stats())
        groups.append(coin_groups[symbol])
        exit_groups.setdefault(reason, _empty_trade_stats())
        groups.append(exit_groups[reason])
        for stats in groups:
            stats["trades"] += 1
            stats["net_pnl"] += pnl
            stats["wins"] += pnl >= 0
            stats["losses"] += pnl < 0
            stats["gross_profit"] += max(pnl, 0.0)
            stats["gross_loss"] += max(-pnl, 0.0)
        execution.append({key: event.get(key) for key in ("symbol", "direction", "price", "pnl", "reason", "intended_risk_amount", "intended_stop_price", "initial_stop_price", "current_stop_price", "initial_stop_gap_pct", "actual_loss_amount", "risk_to_actual_ratio", "stop_gap_pct", "timestamp")})
    return {
        "score_groups": {key: _finalize_trade_stats(value) for key, value in score_groups.items()},
        "tier_groups": {key: _finalize_trade_stats(value) for key, value in tier_groups.items()},
        "direction_groups": {key: _finalize_trade_stats(value) for key, value in direction_groups.items()},
        "coin_groups": {key: _finalize_trade_stats(value) for key, value in sorted(coin_groups.items())},
        "exit_groups": {key: _finalize_trade_stats(value) for key, value in sorted(exit_groups.items())},
        "execution_audit": execution,
    }

def run_multi_asset_paper_session(*, feed, loop: PaperExecutionLoop, duration_seconds: int = 3600, interval_seconds: int = 30, universe: tuple[str, ...] = DEFAULT_LIQUID_UNIVERSE, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> MultiAssetPaperResult:
    if duration_seconds <= 0 or interval_seconds <= 0:
        raise ValueError("duration_seconds and interval_seconds must be positive")
    symbols = tuple(dict.fromkeys(str(symbol).upper() for symbol in universe if symbol))
    if not symbols:
        raise ValueError("universe must not be empty")
    started = clock()
    cycles = successful = errors = 0
    selected: list[str] = []
    history = {symbol: deque(maxlen=max(20, RISK_CONFIG.correlation_window + 12)) for symbol in symbols}
    failure = {symbol: 0 for symbol in symbols}
    quarantined: set[str] = set()
    diagnostics = {"assets_attempted": 0, "liquidity_rejections": 0, "ranked_candidates": 0, "entry_momentum_rejections": 0, "entry_volatility_rejections": 0, "entry_trend_rejections": 0, "entry_overextension_rejections": 0, "entry_reversal_rejections": 0, "pullback_rejections": 0, "bounce_rejections": 0, "ambiguous_direction_rejections": 0, "market_regime_rejections": 0, "correlation_rejections": 0, "sector_rejections": 0, "position_cap_rejections": 0, "entry_ready": 0, "opened_trades": 0, "closed_trades": 0, "signal_exits": 0, "peak_open_positions": 0, "research_gate_rejections": 0, "quarantined_symbols": [], "tier_a_ready": 0, "tier_b_ready": 0, "tier_a_opened": 0, "tier_b_opened": 0, "score_counts": {"3/5": 0, "4/5": 0, "5/5": 0}, "direction_counts": {"LONG": 0, "SHORT": 0}, "opened_direction_counts": {"LONG": 0, "SHORT": 0}}
    while clock() - started < duration_seconds:
        cycles += 1
        snapshots: list[AssetSnapshot] = []
        diagnostics["assets_attempted"] += len(symbols) - len(quarantined)
        for symbol in tuple(loop.account.positions.keys()):
            try:
                snap = feed.snapshot(symbol)
                prices = history[symbol]
                prices.append(float(snap.price))
                atr = max(float(snap.price) * max(float(getattr(snap, "volatility_pct", 0.0)), 0.05) / 100.0 * 0.5, float(snap.price) * 0.001)
                direction = loop.account.positions[symbol].direction
                result = loop.on_market({"symbol": snap.symbol, "price": snap.price, "direction": direction, "stop_distance": max(snap.price * 0.006, atr * 1.8, 1e-8), "atr_distance": atr, "timestamp": snap.timestamp}, exit_signal=exit_signal(list(prices), direction))
                successful += 1
                if result.get("action") == "CLOSE" and result.get("reason") == "SIGNAL":
                    diagnostics["signal_exits"] += 1
            except Exception:
                errors += 1
        for symbol in symbols:
            if symbol in quarantined:
                continue
            try:
                snap = feed.snapshot(symbol)
                price = float(snap.price)
                failure[symbol] = 0
                prices = history[symbol]
                prices.append(price)
                change = ((price / prices[0]) - 1.0) * 100.0 if len(prices) >= 3 else 0.0
                moves = [abs((prices[i] / prices[i - 1] - 1.0) * 100.0) for i in range(1, len(prices))]
                snapshots.append(AssetSnapshot(symbol, price, float(getattr(snap, "quote_volume", 0.0)), change, max(moves, default=0.0)))
                successful += 1
            except Exception:
                errors += 1
                failure[symbol] += 1
                if failure[symbol] >= 3:
                    quarantined.add(symbol)
        ranked = rank_assets(snapshots, min_quote_volume=RESEARCH_MIN_QUOTE_VOLUME, max_candidates=10)
        diagnostics["ranked_candidates"] += len(ranked)
        btc = list(history.get("BTCUSDT", ()))
        btcema = _ema(btc, 20) if len(btc) >= 5 else None
        for candidate in ranked:
            live = next(snapshot for snapshot in snapshots if snapshot.symbol == candidate.symbol)
            prices = list(history[candidate.symbol])
            options = []
            for direction in ("LONG", "SHORT"):
                ready, reason, score, confirmations = entry_signal_details(prices, direction)
                core = confirmations.get("trend") and confirmations.get("medium_momentum") and confirmations.get("microstructure") and confirmations.get("pullback_bounce")
                tier = "A" if ready and score >= TIER_A_MIN_SCORE else ("B" if reason == "momentum_not_confirmed" and score == TIER_B_MIN_SCORE and core else None)
                if tier:
                    options.append((direction, tier, score, reason))
                elif reason == "pullback_not_confirmed":
                    diagnostics["pullback_rejections"] += 1
                elif reason == "bounce_not_confirmed":
                    diagnostics["bounce_rejections"] += 1
                elif reason == "short_term_reversal":
                    diagnostics["entry_reversal_rejections"] += 1
                elif reason == "trend_not_confirmed":
                    diagnostics["entry_trend_rejections"] += 1
                elif reason == "overextended":
                    diagnostics["entry_overextension_rejections"] += 1
                else:
                    diagnostics["entry_momentum_rejections"] += 1
            if not options:
                continue
            best_score = max(option[2] for option in options)
            best_options = [option for option in options if option[2] == best_score]
            if len(best_options) > 1:
                # Never resolve an equal-strength LONG/SHORT tie by iteration
                # order. That would silently reintroduce a LONG bias.
                diagnostics["ambiguous_direction_rejections"] += 1
                continue
            direction, tier, score, _ = best_options[0]
            diagnostics["entry_ready"] += 1
            diagnostics["score_counts"][f"{score}/5"] += 1
            diagnostics[f"tier_{tier.lower()}_ready"] += 1
            diagnostics["direction_counts"][direction] += 1
            if not (RISK_CONFIG.volatility_floor_pct <= live.volatility_pct <= RISK_CONFIG.volatility_ceiling_pct):
                diagnostics["entry_volatility_rejections"] += 1
                continue
            if live.symbol != "BTCUSDT" and btcema is not None:
                btc_ok = btc[-1] >= btcema if direction == "LONG" else btc[-1] <= btcema
                if not btc_ok:
                    diagnostics["market_regime_rejections"] += 1
                    continue
            if live.symbol in loop.account.positions:
                continue
            if len(loop.account.positions) >= RISK_CONFIG.max_open_positions:
                diagnostics["position_cap_rejections"] += 1
                continue
            if sector_position_count(live.symbol, tuple(loop.account.positions.keys())) >= RISK_CONFIG.max_positions_per_sector:
                diagnostics["sector_rejections"] += 1
                continue
            if exceeds_correlation_limit(live.symbol, tuple(loop.account.positions.keys()), history, threshold=RISK_CONFIG.max_pairwise_correlation, window=RISK_CONFIG.correlation_window):
                diagnostics["correlation_rejections"] += 1
                continue
            if live.symbol not in selected:
                selected.append(live.symbol)
            atr = max(live.price * max(live.volatility_pct, 0.05) / 100.0 * 0.5, live.price * 0.001)
            risk = None if tier == "A" else TIER_B_RISK_PCT
            result = loop.on_market({"symbol": live.symbol, "price": live.price, "direction": direction, "stop_distance": max(live.price * 0.006, atr * 1.8, 1e-8), "atr_distance": atr, "timestamp": None, "strategy_score": score, "strategy_tier": tier, "risk_pct_override": risk})
            if result.get("action") == "OPEN":
                diagnostics["opened_trades"] += 1
                diagnostics[f"tier_{tier.lower()}_opened"] += 1
                diagnostics["opened_direction_counts"][direction] += 1
        diagnostics["closed_trades"] = loop.stats.closed_trades
        diagnostics["peak_open_positions"] = max(diagnostics["peak_open_positions"], len(loop.account.positions))
        diagnostics["quarantined_symbols"] = sorted(quarantined)
        remaining = duration_seconds - (clock() - started)
        if remaining <= 0:
            break
        sleep(min(interval_seconds, remaining))
    diagnostics.update(_audit_diagnostics(loop.account.audit_log))
    return MultiAssetPaperResult(duration_seconds // 60, len(symbols), cycles, successful, errors, tuple(selected), loop.summary(mark_price=None), diagnostics)
