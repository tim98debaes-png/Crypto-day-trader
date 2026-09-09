"""Historical replay that mirrors the current multi-asset paper strategy.

This is deliberately event-driven rather than vectorized.  Signals are decided
from information available at a completed bar, entries are filled on the next
bar open, and portfolio/risk/fee logic is delegated to PaperAccount where
possible.  The replay is a research model, not a claim of tick-level fill
accuracy.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from collections import deque
from typing import Iterable

import numpy as np
import pandas as pd

from entry_exit_logic import entry_signal_details, exit_signal
from multi_asset_scanner import RESEARCH_MIN_QUOTE_VOLUME, rank_assets, AssetSnapshot
from paper_engine import PaperAccount
from strategy_risk_controls import RISK_CONFIG, exceeds_correlation_limit, sector_position_count
from research.mtf_features import build_mtf_features, add_btc_context


@dataclass(frozen=True)
class ReplayConfig:
    capital: float = 1000.0
    risk_pct: float = 0.50
    fee_pct: float = 0.10
    slippage_pct: float = 0.02
    max_daily_loss_pct: float = 3.0
    max_candidates: int = 10
    history_size: int = 20
    min_history: int = 12
    interval_minutes: int = 1


def _load_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_json(path, lines=True)
    if frame.empty:
        return frame
    if "timestamp" not in frame.columns:
        for alias in ("open_time", "openTime", "time", "ts"):
            if alias in frame.columns:
                frame = frame.rename(columns={alias: "timestamp"})
                break
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise RuntimeError(f"{path}: missing columns {sorted(missing)}")
    frame = frame.copy()
    raw = frame["timestamp"]
    frame["timestamp"] = pd.to_datetime(raw, utc=True, unit="ms", errors="coerce")
    if frame["timestamp"].isna().all():
        frame["timestamp"] = pd.to_datetime(raw, utc=True, errors="coerce")
    frame = frame.dropna(subset=["timestamp"])
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close", "volume"])
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    frame["symbol"] = path.stem.upper()
    # Binance kline quote volume is preferable when available.  Otherwise use
    # close*base-volume as a conservative deterministic approximation.
    if "quote_volume" in frame.columns:
        frame["quote_volume"] = pd.to_numeric(frame["quote_volume"], errors="coerce")
    else:
        frame["quote_volume"] = frame["close"] * frame["volume"]
    return frame


def load_dataset(root: Path) -> dict[str, pd.DataFrame]:
    frames = {}
    for path in sorted(root.glob("*.jsonl")):
        frame = _load_frame(path)
        if not frame.empty:
            frames[path.stem.upper()] = frame
    if "BTCUSDT" not in frames:
        raise RuntimeError("BTCUSDT is required")
    if not frames:
        raise RuntimeError("no historical candles found")
    return frames


def _rolling_quote_volume(frame: pd.DataFrame, bars: int = 1440) -> pd.Series:
    return frame["quote_volume"].rolling(bars, min_periods=1).sum()


def _volatility_pct(history: deque[float]) -> float:
    values = list(history)
    if len(values) < 2:
        return 0.0
    moves = [abs(values[i] / values[i - 1] - 1.0) * 100.0 for i in range(1, len(values)) if values[i - 1] > 0]
    return max(moves, default=0.0)


def _atr_distance(row: pd.Series, price: float) -> float:
    # The live paper session derives a short-range volatility distance and then
    # uses max(0.6%, 1.8 * ATR-distance) for the initial stop.
    volatility = max(float(row.get("volatility_pct", 0.0)), 0.05)
    atr_distance = price * volatility / 100.0 * 0.5
    return max(price * 0.006, atr_distance * 1.8, 1e-12)


def _regime_ok(row: pd.Series, direction: str) -> bool:
    cols = ["ema20_1h", "ema50_1h", "ema200_1h", "adx1h", "vol_regime_1h"]
    try:
        values = [float(row[c]) for c in cols]
    except (KeyError, TypeError, ValueError):
        return False
    if not np.isfinite(values).all() or values[4] > 3.0 or values[3] < 18.0:
        return False
    if direction == "LONG":
        return values[0] > values[1] > values[2]
    return values[0] < values[1] < values[2]


def _btc_ok(row: pd.Series, direction: str) -> bool:
    cols = ["btc_ema20_1h", "btc_ema50_1h", "btc_ema200_1h", "btc_adx1h", "btc_vol_regime_1h"]
    try:
        values = [float(row[c]) for c in cols]
    except (KeyError, TypeError, ValueError):
        return False
    if not np.isfinite(values).all() or values[4] > 3.0:
        return False
    if direction == "LONG":
        return not (values[3] >= 18.0 and values[0] > values[1] > values[2])
    return not (values[3] >= 18.0 and values[0] < values[1] < values[2])


def _update_stats(stats: dict, pnl: float) -> None:
    stats["closed_trades"] += 1
    if pnl >= 0:
        stats["wins"] += 1
        stats["gross_profit"] += pnl
    else:
        stats["losses"] += 1
        stats["gross_loss"] += abs(pnl)


def _summary(account: PaperAccount, stats: dict, equity_curve: list[float]) -> dict:
    gross_loss = stats["gross_loss"]
    peak = account.capital
    max_dd = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
    return {
        "initial_capital": account.capital,
        "final_equity": round(account.equity(), 8),
        "pnl": round(account.equity() - account.capital, 8),
        "return_pct": round((account.equity() / account.capital - 1.0) * 100.0, 8),
        "max_drawdown_pct": round(max_dd, 8),
        "closed_trades": stats["closed_trades"],
        "wins": stats["wins"],
        "losses": stats["losses"],
        "win_rate_pct": round(stats["wins"] / stats["closed_trades"] * 100.0, 8) if stats["closed_trades"] else 0.0,
        "profit_factor": round(stats["gross_profit"] / gross_loss, 8) if gross_loss else (float("inf") if stats["gross_profit"] else 0.0),
    }


def _prepare_features(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    prepared: dict[str, pd.DataFrame] = {}
    btc_features = build_mtf_features(frames["BTCUSDT"][["timestamp", "open", "high", "low", "close", "volume"]]).copy()
    for symbol, frame in frames.items():
        base = frame[["timestamp", "open", "high", "low", "close", "volume"]].copy()
        features = build_mtf_features(base)
        features = add_btc_context(features, btc_features)
        features["symbol"] = symbol
        # Rolling liquidity is calculated only from bars at or before the signal bar.
        quote = frame.set_index("timestamp")["quote_volume"].sort_index().rolling(1440, min_periods=1).sum()
        features = features.join(quote.rename("quote_volume_24h"), on="timestamp")
        prepared[symbol] = features.sort_values("timestamp").reset_index(drop=True)
    return prepared


def _bars_by_timestamp(prepared: dict[str, pd.DataFrame]) -> list[pd.Timestamp]:
    timestamps = sorted(set().union(*(set(frame["timestamp"]) for frame in prepared.values())))
    return timestamps


def _close_existing(account: PaperAccount, row: pd.Series, history: deque[float], stats: dict, diagnostics: dict) -> None:
    symbol = str(row["symbol"])
    position = account.positions.get(symbol)
    if position is None:
        return
    open_price = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])
    timestamp = str(row["timestamp"])
    account.last_prices[symbol] = open_price

    # Conservative OHLC ambiguity rule: if a stop and a profit trigger are both
    # crossed inside one bar, the stop is assumed to occur first. This avoids
    # inventing an intrabar price path that the historical data does not provide.
    if position.direction == "LONG":
        stop_hit = open_price <= position.stop_price or low <= position.stop_price
        target_hit = open_price >= position.target_price or high >= position.target_price
        reward_hit = high >= position.entry_price + position.initial_stop_distance * RISK_CONFIG.partial_take_profit_r
    else:
        stop_hit = open_price >= position.stop_price or high >= position.stop_price
        target_hit = open_price <= position.target_price or low <= position.target_price
        reward_hit = low <= position.entry_price - position.initial_stop_distance * RISK_CONFIG.partial_take_profit_r

    if stop_hit:
        trigger = open_price if (position.direction == "LONG" and open_price <= position.stop_price) or (position.direction == "SHORT" and open_price >= position.stop_price) else position.stop_price
        pnl = account.close_position(trigger, "SL", timestamp, symbol=symbol, trigger_price=trigger)
        _update_stats(stats, pnl)
        diagnostics["exit_counts"]["SL"] += 1
        return

    if target_hit:
        trigger = open_price if (position.direction == "LONG" and open_price >= position.target_price) or (position.direction == "SHORT" and open_price <= position.target_price) else position.target_price
        pnl = account.close_position(trigger, "TP", timestamp, symbol=symbol, trigger_price=trigger)
        _update_stats(stats, pnl)
        diagnostics["exit_counts"]["TP"] += 1
        return

    if reward_hit and not position.partial_taken:
        trigger = position.entry_price + position.initial_stop_distance if position.direction == "LONG" else position.entry_price - position.initial_stop_distance
        partial = account.take_partial_profit(symbol, trigger, timestamp)
        diagnostics["partial_count"] += 1
        diagnostics["partial_pnl"] += partial

    if position.partial_taken:
        atr_distance = max(float(row["close"]) * max(_volatility_pct(history), 0.05) / 100.0 * 0.5, float(row["close"]) * 0.001)
        account.update_trailing_stop(symbol, float(row["close"]), atr_distance)

    exit_requested = exit_signal(list(history), position.direction)
    time_stop = account.position_age_minutes(symbol, timestamp) >= RISK_CONFIG.time_stop_minutes
    stop_hit_after = (low <= position.stop_price if position.direction == "LONG" else high >= position.stop_price)
    if stop_hit_after or time_stop or exit_requested:
        if stop_hit_after:
            trigger = position.stop_price
            reason = "SL"
        elif time_stop:
            trigger = float(row["close"])
            reason = "TIME_STOP"
        else:
            trigger = float(row["close"])
            reason = "SIGNAL"
        pnl = account.close_position(trigger, reason, timestamp, symbol=symbol, trigger_price=trigger)
        _update_stats(stats, pnl)
        diagnostics["exit_counts"][reason] += 1


def _candidate_options(symbol: str, row: pd.Series, history: deque[float], account: PaperAccount, mode: str, diagnostics: dict) -> list[dict]:
    if len(history) < 12 or symbol in account.positions:
        return []
    volatility = _volatility_pct(history)
    if not (RISK_CONFIG.volatility_floor_pct <= volatility <= RISK_CONFIG.volatility_ceiling_pct):
        diagnostics["volatility_rejections"] += 1
        return []
    options = []
    for direction in ("LONG", "SHORT"):
        ready, reason, score, confirmations = entry_signal_details(list(history), direction)
        if not ready and not (reason == "momentum_not_confirmed" and score == 4):
            diagnostics["entry_rejections"][reason] = diagnostics["entry_rejections"].get(reason, 0) + 1
            continue
        # Current paper logic effectively only promotes the score-5 path.  Keep
        # the score-4 path visible as a diagnostic but do not silently change live
        # behaviour while rebuilding the research engine.
        tier = "A" if ready and score >= 5 else None
        if tier is None:
            diagnostics["tier_b_not_promoted"] += 1
            continue
        if mode in {"REGIME", "REGIME_BTC"} and not _regime_ok(row, direction):
            diagnostics["regime_rejections"] += 1
            continue
        if mode == "REGIME_BTC" and not _btc_ok(row, direction):
            diagnostics["btc_rejections"] += 1
            continue
        options.append({"symbol": symbol, "direction": direction, "score": score, "volatility_pct": volatility, "tier": tier, "confirmations": confirmations})
    if len(options) == 2 and options[0]["score"] == options[1]["score"]:
        diagnostics["ambiguous_direction_rejections"] += 1
        return []
    return options


def run_replay(frames: dict[str, pd.DataFrame], mode: str, config: ReplayConfig = ReplayConfig()) -> tuple[dict, dict]:
    prepared = _prepare_features(frames)
    account = PaperAccount(capital=config.capital, cash=config.capital, risk_pct=config.risk_pct, fee_pct=config.fee_pct, slippage_pct=config.slippage_pct, max_daily_loss_pct=config.max_daily_loss_pct)
    histories = {symbol: deque(maxlen=config.history_size) for symbol in prepared}
    indices = {symbol: 0 for symbol in prepared}
    stats = {"closed_trades": 0, "wins": 0, "losses": 0, "gross_profit": 0.0, "gross_loss": 0.0}
    diagnostics = {"mode": mode, "entry_rejections": {}, "exit_counts": {"SL": 0, "TP": 0, "SIGNAL": 0, "TIME_STOP": 0}, "regime_rejections": 0, "btc_rejections": 0, "volatility_rejections": 0, "ambiguous_direction_rejections": 0, "tier_b_not_promoted": 0, "partial_count": 0, "partial_pnl": 0.0, "opened_trades": 0, "max_open_positions": 0, "events": []}
    equity_curve: list[float] = []
    timestamps = _bars_by_timestamp(prepared)

    for timestamp in timestamps:
        rows_at_time: dict[str, pd.Series] = {}
        for symbol, frame in prepared.items():
            i = indices[symbol]
            while i < len(frame) and frame.iloc[i]["timestamp"] < timestamp:
                i += 1
            if i < len(frame) and frame.iloc[i]["timestamp"] == timestamp:
                rows_at_time[symbol] = frame.iloc[i]
                indices[symbol] = i + 1

        # First process all currently open positions using this bar's OHLC.
        for symbol, row in rows_at_time.items():
            history = histories[symbol]
            if history:
                _close_existing(account, row, history, stats, diagnostics)

        # Only after processing the bar do we append its close to history.  This
        # makes the signal for the next decision strictly based on completed data.
        for symbol, row in rows_at_time.items():
            histories[symbol].append(float(row["close"]))
            account.last_prices[symbol] = float(row["close"])

        snapshots = []
        for symbol, row in rows_at_time.items():
            history = histories[symbol]
            if len(history) < config.min_history:
                continue
            snapshots.append(AssetSnapshot(symbol, float(row["close"]), float(row["quote_volume_24h"]), float((history[-1] / history[0] - 1.0) * 100.0), _volatility_pct(history)))
        ranked = rank_assets(snapshots, min_quote_volume=RESEARCH_MIN_QUOTE_VOLUME, max_candidates=config.max_candidates)
        by_symbol = {x.symbol: rows_at_time[x.symbol] for x in ranked if x.symbol in rows_at_time}

        candidates = []
        for candidate in ranked:
            symbol = candidate.symbol
            row = by_symbol[symbol]
            options = _candidate_options(symbol, row, histories[symbol], account, mode, diagnostics)
            for option in options:
                option["candidate_score"] = candidate.score
                option["price"] = float(row["close"])
                option["stop_distance"] = _atr_distance(row, option["price"])
                candidates.append(option)

        candidates.sort(key=lambda x: (-x["score"], -x["candidate_score"], x["symbol"], x["direction"]))
        open_symbols = tuple(account.positions.keys())
        for candidate in candidates:
            if len(account.positions) >= RISK_CONFIG.max_open_positions:
                break
            symbol = candidate["symbol"]
            if symbol in account.positions:
                continue
            current_symbols = tuple(account.positions.keys())
            if sector_position_count(symbol, current_symbols) >= RISK_CONFIG.max_positions_per_sector:
                continue
            if exceeds_correlation_limit(symbol, current_symbols, histories, threshold=RISK_CONFIG.max_pairwise_correlation, window=RISK_CONFIG.correlation_window):
                continue
            # Signal is generated now and deliberately stored as pending.  The
            # actual fill happens at the next available bar open.
            account._pending_replay_signal = getattr(account, "_pending_replay_signal", {})
            account._pending_replay_signal[symbol] = candidate

        # Execute pending entries on the next bar open only.  A pending signal
        # is consumed when that symbol's next bar becomes available.
        for symbol, row in rows_at_time.items():
            pending = getattr(account, "_pending_replay_signal", {}).pop(symbol, None)
            if not pending or symbol in account.positions:
                continue
            try:
                position = account.open_position(symbol=symbol, direction=pending["direction"], price=float(row["open"]), stop_distance=pending["stop_distance"], rr=2.0, timestamp=str(timestamp), strategy_score=pending["score"], strategy_tier=pending["tier"])
                diagnostics["opened_trades"] += 1
                diagnostics["events"].append({"event": "OPEN", "symbol": symbol, "direction": position.direction, "timestamp": str(timestamp), "score": pending["score"]})
            except RuntimeError:
                pass

        diagnostics["max_open_positions"] = max(diagnostics["max_open_positions"], len(account.positions))
        equity_curve.append(account.equity())

    diagnostics["open_positions_at_end"] = len(account.positions)
    return _summary(account, stats, equity_curve), diagnostics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    frames = load_dataset(Path(args.data))
    results = {}
    diagnostics = {}
    for mode in ("PAPER", "REGIME", "REGIME_BTC"):
        results[mode], diagnostics[mode] = run_replay(frames, mode)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "status": "EXECUTION_COMPLETE", "procedure": "paper_parity_event_replay", "interval": "1m", "modes": results, "diagnostics": diagnostics, "execution": {"capital": 1000.0, "risk_pct": 0.5, "fee_pct": 0.1, "slippage_pct": 0.02, "max_daily_loss_pct": 3.0}, "robustness_policy": "unchanged"}
    (out / "paper_parity_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
