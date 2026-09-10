"""Event-driven 1m replay for the independent Strategy V2 signal engine.

Signals are generated only from completed 5m/15m/1h candles and filled on the
next 1m bar open. Existing PaperAccount execution/risk controls are reused;
legacy entry/exit logic is not imported by this module.
"""
from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path

import pandas as pd

from paper_engine import PaperAccount
from research.paper_parity_replay import (
    ReplayConfig,
    _manage_position,
    _record,
    _stats,
    _summary,
    load_dataset,
)
from strategy_risk_controls import RISK_CONFIG, exceeds_correlation_limit, sector_position_count
from strategy_v2 import generate_signal


def _resample(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    f = frame.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
    out = f.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna().reset_index()
    return out


def _completed(series: pd.DataFrame, timestamp: pd.Timestamp, count: int = 30) -> list[dict]:
    ready = series[series["timestamp"] < timestamp].tail(count)
    return ready.to_dict("records")


def _signal_candidates(
    symbol: str,
    row: pd.Series,
    timestamp: pd.Timestamp,
    bars: dict[str, dict[str, pd.DataFrame]],
    account: PaperAccount,
    history: dict[str, deque[float]],
    btc_bars: dict[str, pd.DataFrame],
    diagnostics: dict,
) -> list[dict]:
    if symbol in account.positions or len(history[symbol]) < 20:
        return []
    if not RISK_CONFIG.volatility_floor_pct <= _volatility(history[symbol]) <= RISK_CONFIG.volatility_ceiling_pct:
        diagnostics["volatility_rejections"] += 1
        return []
    c5 = _completed(bars[symbol]["5m"], timestamp)
    c15 = _completed(bars[symbol]["15m"], timestamp)
    c1 = _completed(bars[symbol]["1h"], timestamp)
    btc1 = _completed(btc_bars["1h"], timestamp) if btc_bars else None
    if min(len(c5), len(c15), len(c1)) < 30:
        diagnostics["insufficient_mtf"] += 1
        return []
    signal = generate_signal(c5, c15, c1, btc1)
    if signal is None:
        diagnostics["no_signal"] += 1
        return []
    diagnostics["signals"] += 1
    return [{
        "symbol": symbol,
        "direction": signal.direction,
        "score": signal.score,
        "stop_distance": signal.stop_distance,
    }]


def _volatility(history: deque[float]) -> float:
    values = list(history)
    if len(values) < 2:
        return 0.0
    return max((abs(values[i] / values[i - 1] - 1.0) * 100.0 for i in range(1, len(values)) if values[i - 1] > 0), default=0.0)


def run_v2(frames: dict[str, pd.DataFrame], config: ReplayConfig = ReplayConfig()) -> tuple[dict, dict]:
    bars = {
        symbol: {"5m": _resample(frame, "5min"), "15m": _resample(frame, "15min"), "1h": _resample(frame, "1h")}
        for symbol, frame in frames.items()
    }
    btc_bars = bars["BTCUSDT"]
    account = PaperAccount(capital=config.capital, cash=config.capital, risk_pct=config.risk_pct, fee_pct=config.fee_pct, slippage_pct=config.slippage_pct, max_daily_loss_pct=config.max_daily_loss_pct)
    history = {symbol: deque(maxlen=20) for symbol in frames}
    cursor = {symbol: 0 for symbol in frames}
    pending: dict[str, dict] = {}
    stats = _stats()
    diagnostics = {"strategy": "V2", "signals": 0, "opened_trades": 0, "no_signal": 0, "insufficient_mtf": 0, "volatility_rejections": 0, "max_open_positions": 0, "exits": {"SL": 0, "TP": 0, "TIME_STOP": 0}}
    curve: list[float] = []
    timestamps = sorted(set().union(*(set(frame["timestamp"]) for frame in frames.values())))

    for timestamp in timestamps:
        rows: dict[str, pd.Series] = {}
        for symbol, frame in frames.items():
            i = cursor[symbol]
            while i < len(frame) and frame.iloc[i]["timestamp"] < timestamp:
                i += 1
            if i < len(frame) and frame.iloc[i]["timestamp"] == timestamp:
                rows[symbol] = frame.iloc[i]
                cursor[symbol] = i + 1

        for symbol, signal in list(pending.items()):
            row = rows.get(symbol)
            if row is None or symbol in account.positions:
                continue
            try:
                account.open_position(symbol=symbol, direction=signal["direction"], price=float(row["open"]), stop_distance=signal["stop_distance"], rr=2.0, timestamp=str(timestamp), strategy_score=signal["score"], strategy_tier="V2")
                diagnostics["opened_trades"] += 1
            except RuntimeError:
                pass
            del pending[symbol]

        for symbol, row in rows.items():
            if symbol in account.positions:
                account.last_prices[symbol] = float(row["open"])
                _manage_position(account, row, history[symbol], stats, diagnostics)

        for symbol, row in rows.items():
            history[symbol].append(float(row["close"]))
            account.last_prices[symbol] = float(row["close"])

        for symbol, row in rows.items():
            position = account.positions.get(symbol)
            if position is not None and account.position_age_minutes(symbol, str(timestamp)) >= RISK_CONFIG.time_stop_minutes:
                _record(stats, account.close_position(float(row["close"]), "TIME_STOP", str(timestamp), symbol=symbol, trigger_price=float(row["close"])))
                diagnostics["exits"]["TIME_STOP"] += 1

        candidates: list[dict] = []
        for symbol, row in rows.items():
            candidates.extend(_signal_candidates(symbol, row, timestamp, bars, account, history, btc_bars, diagnostics))
        candidates.sort(key=lambda x: (-x["score"], x["symbol"], x["direction"]))
        for candidate in candidates:
            if len(account.positions) + len(pending) >= RISK_CONFIG.max_open_positions:
                break
            symbol = candidate["symbol"]
            if symbol in account.positions or symbol in pending:
                continue
            open_symbols = tuple(account.positions.keys())
            if sector_position_count(symbol, open_symbols) >= RISK_CONFIG.max_positions_per_sector:
                continue
            if exceeds_correlation_limit(symbol, open_symbols, history, threshold=RISK_CONFIG.max_pairwise_correlation, window=RISK_CONFIG.correlation_window):
                continue
            pending[symbol] = candidate
        diagnostics["max_open_positions"] = max(diagnostics["max_open_positions"], len(account.positions))
        curve.append(account.equity())

    return _summary(account, stats, curve), diagnostics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    frames = load_dataset(Path(args.data))
    result, diagnostics = run_v2(frames)
    report = {
        "schema_version": 1,
        "status": "EXECUTION_COMPLETE",
        "procedure": "strategy_v2_event_replay",
        "data_interval": "1m",
        "strategy": "V2",
        "execution": {"capital": 1000.0, "risk_pct": 0.5, "fee_pct": 0.1, "slippage_pct": 0.02, "max_daily_loss_pct": 3.0},
        "result": result,
        "diagnostics": diagnostics,
        "robustness_policy": "unchanged",
    }
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "strategy_v2_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
