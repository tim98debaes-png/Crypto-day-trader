"""Event-driven replay for the Strategy V3 decision layer.

The replay intentionally reuses the existing PaperAccount execution engine so
V3 is tested with the same fees, slippage, partials, trailing stops and
portfolio safeguards that will later be used by paper/live execution.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path

import pandas as pd

from paper_engine import PaperAccount
from research.paper_parity_replay import ReplayConfig, _record, _stats, _summary, load_dataset
from research.strategy_v2_metrics import build_metrics
from research.strategy_v2_monte_carlo import bootstrap_monte_carlo
from strategy_v3 import V3Config, _atr, score_setup, select_setup, position_risk_pct
from v3_exit_engine import adaptive_exit_policy
from v3_portfolio_risk import PortfolioSnapshot, admit
from v3_trade_forensics import analyze_trade, summarize as summarize_forensics, to_dicts


def _resample(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    f = frame.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
    return f.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna().reset_index()


def _completed(series: pd.DataFrame, timestamp: pd.Timestamp, count: int = 60) -> list[dict]:
    """Return only bars whose opening timestamp is strictly before decision time."""
    return series[series["timestamp"] < timestamp].tail(count).to_dict("records")


def _price_history(histories: dict[str, deque[float]]) -> dict[str, list[float]]:
    return {symbol: list(values) for symbol, values in histories.items()}


def _candidate(symbol, timestamp, bars, account, histories, btc_bars, config, diagnostics):
    if symbol == "BTCUSDT" or symbol in account.positions or len(histories[symbol]) < 20:
        return None
    c5 = _completed(bars[symbol]["5m"], timestamp)
    c15 = _completed(bars[symbol]["15m"], timestamp)
    c1 = _completed(bars[symbol]["1h"], timestamp)
    btc1 = _completed(btc_bars["1h"], timestamp)
    if min(len(c5), len(c15), len(c1)) < 55:
        diagnostics["insufficient_mtf"] += 1
        return None
    long_setup = score_setup(c5, c15, c1, "LONG", btc1, config)
    short_setup = score_setup(c5, c15, c1, "SHORT", btc1, config)
    setup = select_setup(long_setup, short_setup)
    if setup is None or setup.score < config.min_setup_score:
        diagnostics["below_threshold"] += 1
        return None
    atr = float(setup.features.get("atr", 0.0))
    if atr <= 0:
        diagnostics["invalid_atr"] += 1
        return None
    risk_pct = position_risk_pct(setup, config)
    histories_dict = _price_history(histories)
    snapshot = PortfolioSnapshot(account.equity(), tuple(account.positions.keys()), account.open_risk_pct())
    admission = admit(
        symbol,
        risk_pct,
        snapshot,
        histories_dict,
        max_positions=config.max_open_positions,
        max_total_risk_pct=config.max_total_open_risk_pct,
        max_sector_positions=config.max_positions_per_sector,
        max_correlation=config.max_correlation,
        correlation_window=config.correlation_window,
    )
    if not admission.allowed:
        diagnostics["portfolio_rejections"][admission.reason] += 1
        return None
    diagnostics["signals"] += 1
    return {
        "symbol": symbol,
        "direction": setup.direction,
        "score": setup.score,
        "atr": atr,
        "risk_pct": risk_pct,
        "regime": setup.regime,
    }


def run_v3(frames: dict[str, pd.DataFrame], config: ReplayConfig = ReplayConfig(), v3: V3Config = V3Config()) -> tuple[dict, dict]:
    bars = {symbol: {"5m": _resample(frame, "5min"), "15m": _resample(frame, "15min"), "1h": _resample(frame, "1h")} for symbol, frame in frames.items()}
    btc_bars = bars["BTCUSDT"]
    account = PaperAccount(
        capital=config.capital,
        cash=config.capital,
        risk_pct=config.risk_pct,
        fee_pct=config.fee_pct,
        slippage_pct=config.slippage_pct,
        max_daily_loss_pct=config.max_daily_loss_pct,
    )
    histories = {symbol: deque(maxlen=60) for symbol in frames}
    atr_by_symbol = defaultdict(float)
    cursor = {symbol: 0 for symbol in frames}
    pending = {}
    stats = _stats()
    diagnostics = {
        "strategy": "V3",
        "signals": 0,
        "opened_trades": 0,
        "below_threshold": 0,
        "insufficient_mtf": 0,
        "invalid_atr": 0,
        "portfolio_rejections": defaultdict(int),
        "partials": 0,
        "partial_pnl": 0.0,
        "max_open_positions": 0,
        "exits": {"SL": 0, "TP": 0, "SIGNAL": 0, "TIME_STOP": 0, "ADAPTIVE_PARTIAL": 0, "ADAPTIVE_TIME_STOP": 0, "ADAPTIVE_CLOSE": 0},
        "exit_policy_decisions": defaultdict(int),
        "regime_trade_counts": defaultdict(int),
    }
    curve = []
    active_paths: dict[str, list[float]] = {}
    active_meta: dict[str, dict] = {}
    forensic_records = []

    def record_close(symbol: str, exit_price: float, reason: str, timestamp: str) -> None:
        if symbol not in active_meta:
            return
        meta = active_meta[symbol]
        path = active_paths.get(symbol, [])
        if path and (not path or path[-1] != exit_price):
            path = [*path, exit_price]
        elif path:
            path = list(path)
        forensic_records.append(
            analyze_trade(
                meta["direction"],
                meta["entry"],
                exit_price,
                meta["stop_distance"],
                path,
                reason,
            )
        )
        diagnostics["regime_trade_counts"][meta["regime"]] += 1
        active_meta.pop(symbol, None)
        active_paths.pop(symbol, None)

    timestamps = sorted(set().union(*(set(frame["timestamp"]) for frame in frames.values())))
    for timestamp in timestamps:
        rows = {}
        for symbol, frame in frames.items():
            i = cursor[symbol]
            while i < len(frame) and frame.iloc[i]["timestamp"] < timestamp:
                i += 1
            if i < len(frame) and frame.iloc[i]["timestamp"] == timestamp:
                rows[symbol] = frame.iloc[i]
                cursor[symbol] = i + 1

        for symbol, candidate in list(pending.items()):
            row = rows.get(symbol)
            if row is None or symbol in account.positions:
                continue
            stop_distance = min(candidate["atr"] * v3.stop_atr_multiple, float(row["open"]) * v3.max_stop_pct)
            try:
                account.open_position(
                    symbol=symbol,
                    direction=candidate["direction"],
                    price=float(row["open"]),
                    stop_distance=stop_distance,
                    rr=2.0,
                    timestamp=str(timestamp),
                    strategy_score=int(candidate["score"] * 100),
                    strategy_tier=f"V3_{candidate['regime']}",
                    risk_pct_override=candidate["risk_pct"],
                )
                diagnostics["opened_trades"] += 1
                position = account.positions[symbol]
                active_paths[symbol] = [position.entry_price]
                active_meta[symbol] = {
                    "direction": position.direction,
                    "entry": position.entry_price,
                    "stop_distance": position.initial_stop_distance,
                    "regime": candidate["regime"],
                }
            except (RuntimeError, ValueError):
                pass
            del pending[symbol]

        for symbol, row in rows.items():
            histories[symbol].append(float(row["close"]))
            account.last_prices[symbol] = float(row["close"])
            if symbol in account.positions:
                active_paths.setdefault(symbol, [account.positions[symbol].entry_price]).append(float(row["close"]))
                c5 = _completed(bars[symbol]["5m"], timestamp)
                atr = _atr(c5) or atr_by_symbol[symbol]
                atr_by_symbol[symbol] = atr
                position = account.positions[symbol]
                if atr > 0:
                    account.update_trailing_stop(symbol, float(row["close"]), atr)
                stop = position.stop_price
                if (position.direction == "LONG" and float(row["low"]) <= stop) or (position.direction == "SHORT" and float(row["high"]) >= stop):
                    _record(stats, account.close_position(stop, "SL", str(timestamp), symbol=symbol, trigger_price=stop))
                    diagnostics["exits"]["SL"] += 1
                    record_close(symbol, stop, "SL", str(timestamp))
                    continue
                setup_score = float(next((e.get("strategy_score", 0) for e in reversed(account.audit_log) if e.get("event") == "OPEN" and e.get("symbol") == symbol), 0)) / 100.0
                bars_open = int(account.position_age_minutes(symbol, str(timestamp)) / 5)
                if atr > 0:
                    decision = adaptive_exit_policy(
                        position.direction,
                        position.entry_price,
                        float(row["close"]),
                        stop,
                        bars_open,
                        setup_score,
                        active_meta.get(symbol, {}).get("regime", "TRANSITION"),
                        v3,
                        risk_distance=active_meta.get(symbol, {}).get("stop_distance"),
                    )
                    diagnostics["exit_policy_decisions"][decision.action] += 1
                    if decision.action == "PARTIAL":
                        reason = "ADAPTIVE_PARTIAL"
                        if not position.partial_taken:
                            pnl = account.take_partial_profit(symbol, float(row["close"]), str(timestamp))
                            diagnostics["partials"] += 1
                            diagnostics["partial_pnl"] += pnl
                    elif decision.action == "CLOSE":
                        reason = decision.reason
                        _record(stats, account.close_position(float(row["close"]), reason, str(timestamp), symbol=symbol, trigger_price=float(row["close"])))
                        diagnostics["exits"][reason] += 1
                        record_close(symbol, float(row["close"]), reason, str(timestamp))
                        continue

        for symbol, row in rows.items():
            position = account.positions.get(symbol)
            if position is not None and account.position_age_minutes(symbol, str(timestamp)) >= v3.time_stop_minutes:
                _record(stats, account.close_position(float(row["close"]), "TIME_STOP", str(timestamp), symbol=symbol, trigger_price=float(row["close"])))
                diagnostics["exits"]["TIME_STOP"] += 1
                record_close(symbol, float(row["close"]), "TIME_STOP", str(timestamp))

        candidates = []
        for symbol in rows:
            candidate = _candidate(symbol, timestamp, bars, account, histories, btc_bars, v3, diagnostics)
            if candidate is not None:
                candidates.append(candidate)
        candidates.sort(key=lambda x: (-x["score"], x["symbol"], x["direction"]))
        for candidate in candidates:
            if len(account.positions) + len(pending) >= v3.max_open_positions:
                break
            symbol = candidate["symbol"]
            if symbol not in account.positions and symbol not in pending:
                pending[symbol] = candidate
        diagnostics["max_open_positions"] = max(diagnostics["max_open_positions"], len(account.positions))
        curve.append(account.equity())

    diagnostics["portfolio_rejections"] = dict(diagnostics["portfolio_rejections"])
    diagnostics["exit_policy_decisions"] = dict(diagnostics["exit_policy_decisions"])
    diagnostics["regime_trade_counts"] = dict(diagnostics["regime_trade_counts"])
    diagnostics["trade_forensics"] = summarize_forensics(forensic_records)
    diagnostics["trade_forensics_records"] = to_dicts(forensic_records)
    diagnostics["robustness_metrics"] = build_metrics(curve, account.audit_log)
    diagnostics["bootstrap_monte_carlo"] = bootstrap_monte_carlo(account.audit_log, initial_capital=config.capital, simulations=1000, seed=42)
    return _summary(account, stats, curve), diagnostics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result, diagnostics = run_v3(load_dataset(Path(args.data)))
    report = {
        "schema_version": 2,
        "status": "EXECUTION_COMPLETE",
        "procedure": "strategy_v3_event_replay",
        "data_interval": "1m",
        "strategy": "V3",
        "execution": {"capital": 1000.0, "risk_pct": 0.5, "fee_pct": 0.1, "slippage_pct": 0.02, "max_daily_loss_pct": 3.0},
        "result": result,
        "diagnostics": diagnostics,
    }
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "strategy_v3_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
