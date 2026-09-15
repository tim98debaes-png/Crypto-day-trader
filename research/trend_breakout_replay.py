"""Cost-aware single-asset replay for the trend-breakout research baseline.

Signals are generated only from a completed candle and executed on the next
candle open. Fees and slippage are charged on entry and exit. If a candle
hits both stop and target, the stop wins (conservative intrabar assumption).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from strategy_trend_breakout import TrendBreakoutConfig, indicators


@dataclass(frozen=True)
class ReplayConfig:
    initial_capital: float = 1000.0
    risk_pct: float = 0.50
    fee_pct: float = 0.10
    slippage_pct: float = 0.02


def _fill(price: float, direction: str, side: str, slippage_pct: float) -> float:
    slip = slippage_pct / 100.0
    if side == "ENTRY":
        return price * (1.0 + slip) if direction == "LONG" else price * (1.0 - slip)
    return price * (1.0 - slip) if direction == "LONG" else price * (1.0 + slip)


def replay_ohlcv(
    df: pd.DataFrame,
    strategy: TrendBreakoutConfig = TrendBreakoutConfig(),
    config: ReplayConfig = ReplayConfig(),
) -> dict:
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    if len(df) < 3:
        return {"initial_capital": config.initial_capital, "final_equity": config.initial_capital, "pnl": 0.0, "closed_trades": 0, "wins": 0, "losses": 0, "profit_factor": 0.0, "max_drawdown_pct": 0.0, "trades": []}
    if config.initial_capital <= 0 or config.risk_pct <= 0 or config.fee_pct < 0 or config.slippage_pct < 0:
        raise ValueError("invalid replay configuration")

    data = indicators(df.reset_index(drop=True), strategy)
    cash = float(config.initial_capital)
    position = None
    pending = None
    trades = []
    curve = []

    def equity(mark: float) -> float:
        if position is None:
            return cash
        gross = ((mark - position["entry"]) if position["direction"] == "LONG" else (position["entry"] - mark)) * position["quantity"]
        return cash + gross

    for i in range(len(data)):
        row = data.iloc[i]

        # A signal from the previous completed candle is executed here, at this
        # candle's open. This is the key anti-look-ahead rule.
        if pending is not None and position is None:
            direction = pending["direction"]
            entry = _fill(float(row["open"]), direction, "ENTRY", config.slippage_pct)
            stop_distance = pending["stop_distance"]
            stop = entry - stop_distance if direction == "LONG" else entry + stop_distance
            target = entry + pending["target_distance"] if direction == "LONG" else entry - pending["target_distance"]
            stop_exit = _fill(stop, direction, "EXIT", config.slippage_pct)
            risk_per_unit = abs(entry - stop_exit) + (entry + stop_exit) * config.fee_pct / 100.0
            risk_amount = cash * config.risk_pct / 100.0
            quantity = risk_amount / risk_per_unit if risk_per_unit > 0 else 0.0
            entry_fee = entry * quantity * config.fee_pct / 100.0
            cash -= entry_fee
            position = {"direction": direction, "entry": entry, "quantity": quantity, "stop": stop, "target": target, "entry_fee": entry_fee, "signal_index": pending["signal_index"]}
            pending = None

        if position is not None:
            direction = position["direction"]
            open_price = float(row["open"]); high = float(row["high"]); low = float(row["low"])
            stop_hit = open_price <= position["stop"] or low <= position["stop"] if direction == "LONG" else open_price >= position["stop"] or high >= position["stop"]
            target_hit = open_price >= position["target"] or high >= position["target"] if direction == "LONG" else open_price <= position["target"] or low <= position["target"]
            reason = None
            trigger = None
            if stop_hit:
                reason, trigger = "SL", open_price if (direction == "LONG" and open_price <= position["stop"]) or (direction == "SHORT" and open_price >= position["stop"]) else position["stop"]
            elif target_hit:
                reason, trigger = "TP", open_price if (direction == "LONG" and open_price >= position["target"]) or (direction == "SHORT" and open_price <= position["target"]) else position["target"]
            if reason is not None:
                exit_price = _fill(float(trigger), direction, "EXIT", config.slippage_pct)
                gross = ((exit_price - position["entry"]) if direction == "LONG" else (position["entry"] - exit_price)) * position["quantity"]
                exit_fee = exit_price * position["quantity"] * config.fee_pct / 100.0
                pnl = gross - position["entry_fee"] - exit_fee
                cash += gross - exit_fee
                trades.append({"entry_index": position["signal_index"] + 1, "exit_index": i, "direction": direction, "entry": position["entry"], "exit": exit_price, "reason": reason, "quantity": position["quantity"], "pnl": pnl})
                position = None

        curve.append(equity(float(row["close"])))

        # The current candle is complete here. Only now can it create a signal
        # for the next candle, and never while a position remains open.
        if position is None and i < len(data) - 1:
            values = data.loc[i, ["close", "ema_fast", "ema_slow", "atr", "atr_pct", "prior_high", "prior_low", "volume_ratio"]]
            if not values.isna().any() and strategy.min_atr_pct <= float(values["atr_pct"]) <= strategy.max_atr_pct and float(values["volume_ratio"]) >= strategy.min_volume_ratio:
                if float(values["close"]) > float(values["prior_high"]) and float(values["ema_fast"]) > float(values["ema_slow"]):
                    pending = {"direction": "LONG", "stop_distance": strategy.stop_atr * float(values["atr"]), "target_distance": strategy.target_r * strategy.stop_atr * float(values["atr"]), "signal_index": i}
                elif float(values["close"]) < float(values["prior_low"]) and float(values["ema_fast"]) < float(values["ema_slow"]):
                    pending = {"direction": "SHORT", "stop_distance": strategy.stop_atr * float(values["atr"]), "target_distance": strategy.target_r * strategy.stop_atr * float(values["atr"]), "signal_index": i}

    if position is not None:
        direction = position["direction"]
        exit_price = _fill(float(data.iloc[-1]["close"]), direction, "EXIT", config.slippage_pct)
        gross = ((exit_price - position["entry"]) if direction == "LONG" else (position["entry"] - exit_price)) * position["quantity"]
        exit_fee = exit_price * position["quantity"] * config.fee_pct / 100.0
        pnl = gross - position["entry_fee"] - exit_fee
        cash += gross - exit_fee
        trades.append({"entry_index": position["signal_index"] + 1, "exit_index": len(data) - 1, "direction": direction, "entry": position["entry"], "exit": exit_price, "reason": "END", "quantity": position["quantity"], "pnl": pnl})
        position = None
        curve[-1] = cash

    wins = sum(t["pnl"] > 0 for t in trades)
    losses = sum(t["pnl"] < 0 for t in trades)
    gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = -sum(t["pnl"] for t in trades if t["pnl"] < 0)
    peak = config.initial_capital
    max_dd = 0.0
    for value in curve:
        peak = max(peak, value)
        max_dd = max(max_dd, (peak - value) / peak * 100.0)
    return {"initial_capital": config.initial_capital, "final_equity": cash, "pnl": cash - config.initial_capital, "closed_trades": len(trades), "wins": wins, "losses": losses, "win_rate_pct": wins / len(trades) * 100.0 if trades else 0.0, "profit_factor": gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0), "max_drawdown_pct": max_dd, "fees_and_slippage_included": True, "trades": trades}
