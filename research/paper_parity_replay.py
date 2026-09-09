"""Event-driven historical replay of the live paper entry/exit lifecycle.

Signals are formed only after a completed 1m bar and are queued for the next
bar. Stops/targets use OHLC with a conservative stop-first rule when a bar
crosses multiple triggers. PaperAccount supplies fees, slippage, sizing,
portfolio caps, cooldowns and daily-loss protection.
"""
from __future__ import annotations

import argparse
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from entry_exit_logic import entry_signal_details, exit_signal
from multi_asset_scanner import AssetSnapshot, RESEARCH_MIN_QUOTE_VOLUME, rank_assets
from paper_engine import PaperAccount
from research.mtf_features import add_btc_context, build_mtf_features
from strategy_risk_controls import RISK_CONFIG, exceeds_correlation_limit, sector_position_count


@dataclass(frozen=True)
class ReplayConfig:
    capital: float = 1000.0
    risk_pct: float = 0.50
    fee_pct: float = 0.10
    slippage_pct: float = 0.02
    max_daily_loss_pct: float = 3.0
    history_size: int = 20
    min_history: int = 12
    max_candidates: int = 10


def load_dataset(root: Path) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for path in sorted(root.glob("*.jsonl")):
        frame = pd.read_json(path, lines=True)
        if frame.empty:
            continue
        if "timestamp" not in frame.columns:
            for alias in ("open_time", "openTime", "time", "ts"):
                if alias in frame.columns:
                    frame = frame.rename(columns={alias: "timestamp"})
                    break
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        missing = required - set(frame.columns)
        if missing:
            raise RuntimeError(f"{path}: missing {sorted(missing)}")
        frame = frame.copy()
        raw = frame["timestamp"]
        frame["timestamp"] = pd.to_datetime(raw, utc=True, unit="ms", errors="coerce")
        if frame["timestamp"].isna().all():
            frame["timestamp"] = pd.to_datetime(raw, utc=True, errors="coerce")
        for col in ("open", "high", "low", "close", "volume"):
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
        frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
        frame = frame.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
        frame["symbol"] = path.stem.upper()
        if "quote_volume" in frame:
            frame["quote_volume"] = pd.to_numeric(frame["quote_volume"], errors="coerce")
        else:
            frame["quote_volume"] = frame["close"] * frame["volume"]
        frames[path.stem.upper()] = frame
    if not frames or "BTCUSDT" not in frames:
        raise RuntimeError("historical dataset must contain BTCUSDT and at least one asset")
    return frames


def _features(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    btc = build_mtf_features(frames["BTCUSDT"][["timestamp", "open", "high", "low", "close", "volume"]])
    result: dict[str, pd.DataFrame] = {}
    for symbol, frame in frames.items():
        f = build_mtf_features(frame[["timestamp", "open", "high", "low", "close", "volume"]])
        f = add_btc_context(f, btc)
        liquidity = frame.set_index("timestamp")["quote_volume"].rolling(1440, min_periods=1).sum()
        f = f.join(liquidity.rename("quote_volume_24h"), on="timestamp")
        f["symbol"] = symbol
        result[symbol] = f.sort_values("timestamp").reset_index(drop=True)
    return result


def _volatility(history: deque[float]) -> float:
    values = list(history)
    if len(values) < 2:
        return 0.0
    return max((abs(values[i] / values[i - 1] - 1.0) * 100.0 for i in range(1, len(values)) if values[i - 1] > 0), default=0.0)


def _ema(values: deque[float], period: int = 20) -> float | None:
    if not values:
        return None
    alpha = 2.0 / (period + 1.0)
    result = values[0]
    for value in list(values)[1:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def _stop_distance(price: float, volatility_pct: float) -> float:
    short_atr = price * max(volatility_pct, 0.05) / 100.0 * 0.5
    return max(price * 0.006, short_atr * 1.8, 1e-12)


def _regime_ok(row: pd.Series, direction: str) -> bool:
    try:
        e20, e50, e200, adx, vol = (float(row[c]) for c in ("ema20_1h", "ema50_1h", "ema200_1h", "adx1h", "vol_regime_1h"))
    except (KeyError, TypeError, ValueError):
        return False
    if not np.isfinite([e20, e50, e200, adx, vol]).all() or adx < 18.0 or vol > 3.0:
        return False
    return e20 > e50 > e200 if direction == "LONG" else e20 < e50 < e200


def _btc_ok(row: pd.Series, direction: str) -> bool:
    try:
        e20, e50, e200, adx, vol = (float(row[c]) for c in ("btc_ema20_1h", "btc_ema50_1h", "btc_ema200_1h", "btc_adx1h", "btc_vol_regime_1h"))
    except (KeyError, TypeError, ValueError):
        return False
    if not np.isfinite([e20, e50, e200, adx, vol]).all() or vol > 3.0:
        return False
    btc_up = adx >= 18.0 and e20 > e50 > e200
    btc_down = adx >= 18.0 and e20 < e50 < e200
    return not (btc_down if direction == "LONG" else btc_up)


def _paper_btc_ok(symbol: str, direction: str, btc_history: deque[float]) -> bool:
    if symbol == "BTCUSDT" or len(btc_history) < 5:
        return True
    btc_price = btc_history[-1]
    btc_ema = _ema(btc_history, 20)
    if btc_ema is None:
        return True
    return btc_price >= btc_ema if direction == "LONG" else btc_price <= btc_ema


def _stats() -> dict:
    return {"closed_trades": 0, "wins": 0, "losses": 0, "gross_profit": 0.0, "gross_loss": 0.0}


def _record(stats: dict, pnl: float) -> None:
    stats["closed_trades"] += 1
    if pnl >= 0:
        stats["wins"] += 1; stats["gross_profit"] += pnl
    else:
        stats["losses"] += 1; stats["gross_loss"] += -pnl


def _summary(account: PaperAccount, stats: dict, curve: list[float]) -> dict:
    peak = account.capital; dd = 0.0
    for value in curve:
        peak = max(peak, value); dd = max(dd, (peak - value) / peak * 100.0)
    gl = stats["gross_loss"]
    return {"initial_capital": account.capital, "final_equity": round(account.equity(), 8), "pnl": round(account.equity() - account.capital, 8), "return_pct": round((account.equity() / account.capital - 1) * 100, 8), "max_drawdown_pct": round(dd, 8), "closed_trades": stats["closed_trades"], "wins": stats["wins"], "losses": stats["losses"], "win_rate_pct": round(stats["wins"] / stats["closed_trades"] * 100, 8) if stats["closed_trades"] else 0.0, "profit_factor": round(stats["gross_profit"] / gl, 8) if gl else (float("inf") if stats["gross_profit"] else 0.0)}


def _manage_position(account: PaperAccount, row: pd.Series, history: deque[float], stats: dict, diag: dict) -> None:
    symbol = str(row["symbol"]); position = account.positions.get(symbol)
    if position is None: return
    open_price, high, low, close = map(float, (row["open"], row["high"], row["low"], row["close"])); timestamp = str(row["timestamp"])
    if position.direction == "LONG":
        stop_hit = open_price <= position.stop_price or low <= position.stop_price; target_hit = open_price >= position.target_price or high >= position.target_price; reward_hit = high >= position.entry_price + position.initial_stop_distance * RISK_CONFIG.partial_take_profit_r
    else:
        stop_hit = open_price >= position.stop_price or high >= position.stop_price; target_hit = open_price <= position.target_price or low <= position.target_price; reward_hit = low <= position.entry_price - position.initial_stop_distance * RISK_CONFIG.partial_take_profit_r
    if stop_hit:
        trigger = open_price if (position.direction == "LONG" and open_price <= position.stop_price) or (position.direction == "SHORT" and open_price >= position.stop_price) else position.stop_price
        _record(stats, account.close_position(trigger, "SL", timestamp, symbol=symbol, trigger_price=trigger)); diag["exits"]["SL"] += 1; return
    if target_hit:
        trigger = open_price if (position.direction == "LONG" and open_price >= position.target_price) or (position.direction == "SHORT" and open_price <= position.target_price) else position.target_price
        _record(stats, account.close_position(trigger, "TP", timestamp, symbol=symbol, trigger_price=trigger)); diag["exits"]["TP"] += 1; return
    if reward_hit and not position.partial_taken:
        trigger = position.entry_price + position.initial_stop_distance if position.direction == "LONG" else position.entry_price - position.initial_stop_distance
        diag["partial_pnl"] += account.take_partial_profit(symbol, trigger, timestamp); diag["partials"] += 1
    if position.partial_taken:
        atr = max(close * max(_volatility(history), 0.05) / 100.0 * 0.5, close * 0.001); account.update_trailing_stop(symbol, close, atr)


def _options(row: pd.Series, history: deque[float], btc_history: deque[float], account: PaperAccount, mode: str, diag: dict) -> list[dict]:
    symbol = str(row["symbol"])
    if symbol in account.positions or len(history) < 12: return []
    vol = _volatility(history)
    if not RISK_CONFIG.volatility_floor_pct <= vol <= RISK_CONFIG.volatility_ceiling_pct:
        diag["volatility_rejections"] += 1; return []
    options = []
    for direction in ("LONG", "SHORT"):
        ready, reason, score, _ = entry_signal_details(list(history), direction)
        if not ready:
            diag["entry_rejections"][reason] = diag["entry_rejections"].get(reason, 0) + 1; continue
        if not _paper_btc_ok(symbol, direction, btc_history):
            diag["paper_btc_rejections"] += 1; continue
        if mode in {"REGIME", "REGIME_BTC"} and not _regime_ok(row, direction):
            diag["regime_rejections"] += 1; continue
        if mode == "REGIME_BTC" and not _btc_ok(row, direction):
            diag["btc_rejections"] += 1; continue
        options.append({"symbol": symbol, "direction": direction, "score": score, "volatility_pct": vol})
    if len(options) == 2:
        return [max(options, key=lambda x: x["score"])] if options[0]["score"] != options[1]["score"] else []
    return options


def run_replay(frames: dict[str, pd.DataFrame], mode: str, config: ReplayConfig = ReplayConfig()) -> tuple[dict, dict]:
    data = _features(frames)
    account = PaperAccount(capital=config.capital, cash=config.capital, risk_pct=config.risk_pct, fee_pct=config.fee_pct, slippage_pct=config.slippage_pct, max_daily_loss_pct=config.max_daily_loss_pct)
    history = {symbol: deque(maxlen=config.history_size) for symbol in data}; cursor = {symbol: 0 for symbol in data}; pending: dict[str, dict] = {}
    stats = _stats(); diag = {"mode": mode, "entry_rejections": {}, "paper_btc_rejections": 0, "regime_rejections": 0, "btc_rejections": 0, "volatility_rejections": 0, "partials": 0, "partial_pnl": 0.0, "exits": {"SL": 0, "TP": 0, "SIGNAL": 0, "TIME_STOP": 0}, "opened_trades": 0, "max_open_positions": 0}
    curve: list[float] = []; timestamps = sorted(set().union(*(set(frame["timestamp"]) for frame in data.values())))
    for timestamp in timestamps:
        rows: dict[str, pd.Series] = {}
        for symbol, frame in data.items():
            i = cursor[symbol]
            while i < len(frame) and frame.iloc[i]["timestamp"] < timestamp: i += 1
            if i < len(frame) and frame.iloc[i]["timestamp"] == timestamp: rows[symbol] = frame.iloc[i]; cursor[symbol] = i + 1
        for symbol, signal in list(pending.items()):
            row = rows.get(symbol)
            if row is None or symbol in account.positions: continue
            try:
                account.open_position(symbol=symbol, direction=signal["direction"], price=float(row["open"]), stop_distance=signal["stop_distance"], rr=2.0, timestamp=str(timestamp), strategy_score=signal["score"], strategy_tier="A")
                diag["opened_trades"] += 1
            except RuntimeError: pass
            del pending[symbol]
        for symbol, row in rows.items():
            if symbol in account.positions:
                account.last_prices[symbol] = float(row["open"]); _manage_position(account, row, history[symbol], stats, diag)
        for symbol, row in rows.items():
            history[symbol].append(float(row["close"])); account.last_prices[symbol] = float(row["close"])
        for symbol, row in rows.items():
            position = account.positions.get(symbol)
            if position is not None and (exit_signal(list(history[symbol]), position.direction) or account.position_age_minutes(symbol, str(timestamp)) >= RISK_CONFIG.time_stop_minutes):
                reason = "TIME_STOP" if account.position_age_minutes(symbol, str(timestamp)) >= RISK_CONFIG.time_stop_minutes else "SIGNAL"
                _record(stats, account.close_position(float(row["close"]), reason, str(timestamp), symbol=symbol, trigger_price=float(row["close"]))); diag["exits"][reason] += 1
        snapshots = []
        for symbol, row in rows.items():
            h = history[symbol]
            if len(h) < config.min_history: continue
            snapshots.append(AssetSnapshot(symbol, float(row["close"]), float(row["quote_volume_24h"]), (h[-1] / h[0] - 1.0) * 100.0, _volatility(h)))
        ranked = rank_assets(snapshots, min_quote_volume=RESEARCH_MIN_QUOTE_VOLUME, max_candidates=config.max_candidates)
        candidates = []
        btc_history = history["BTCUSDT"]
        for ranked_item in ranked:
            row = rows[ranked_item.symbol]
            for option in _options(row, history[ranked_item.symbol], btc_history, account, mode, diag):
                option["candidate_score"] = ranked_item.score; option["stop_distance"] = _stop_distance(float(row["close"]), option["volatility_pct"]); candidates.append(option)
        candidates.sort(key=lambda x: (-x["score"], -x["candidate_score"], x["symbol"], x["direction"]))
        for candidate in candidates:
            if len(account.positions) + len(pending) >= RISK_CONFIG.max_open_positions: break
            symbol = candidate["symbol"]
            if symbol in account.positions or symbol in pending: continue
            open_symbols = tuple(account.positions.keys())
            if sector_position_count(symbol, open_symbols) >= RISK_CONFIG.max_positions_per_sector: continue
            if exceeds_correlation_limit(symbol, open_symbols, history, threshold=RISK_CONFIG.max_pairwise_correlation, window=RISK_CONFIG.correlation_window): continue
            pending[symbol] = candidate
        diag["max_open_positions"] = max(diag["max_open_positions"], len(account.positions)); curve.append(account.equity())
    return _summary(account, stats, curve), diag


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--data", required=True); parser.add_argument("--output", required=True); args = parser.parse_args()
    frames = load_dataset(Path(args.data)); results, diagnostics = {}, {}
    for mode in ("PAPER", "REGIME", "REGIME_BTC"): results[mode], diagnostics[mode] = run_replay(frames, mode)
    report = {"schema_version": 1, "status": "EXECUTION_COMPLETE", "procedure": "paper_parity_event_replay", "data_interval": "1m", "execution": {"capital": 1000.0, "risk_pct": 0.5, "fee_pct": 0.1, "slippage_pct": 0.02, "max_daily_loss_pct": 3.0}, "results": results, "diagnostics": diagnostics, "robustness_policy": "unchanged"}
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True); (output / "paper_parity_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"); print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__": main()
