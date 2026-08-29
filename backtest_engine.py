"""Deterministic historical paper backtesting engine.

The engine reuses PaperAccount execution semantics. Historical exits use OHLC
when available so stops/targets are not missed merely because the candle close
returned inside the range. If both stop and target are touched in one candle,
the stop is selected conservatively because intrabar ordering is unknown.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from paper_engine import PaperAccount

SignalProvider = Callable[[dict], Optional[dict]]

@dataclass
class BacktestResult:
    initial_capital: float
    final_equity: float
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)

    @property
    def pnl(self) -> float:
        return self.final_equity - self.initial_capital

    @property
    def return_pct(self) -> float:
        return (self.final_equity / self.initial_capital - 1.0) * 100.0 if self.initial_capital > 0 else 0.0

    @property
    def max_drawdown_pct(self) -> float:
        peak = self.initial_capital
        maximum = 0.0
        for row in self.equity_curve:
            equity = float(row["equity"])
            peak = max(peak, equity)
            if peak:
                maximum = max(maximum, (peak - equity) / peak * 100.0)
        return maximum

    def summary(self) -> dict:
        closes = [x for x in self.trades if x.get("event") == "CLOSE"]
        wins = [x for x in closes if float(x.get("pnl", 0)) > 0]
        losses = [x for x in closes if float(x.get("pnl", 0)) < 0]
        gross_profit = sum(float(x.get("pnl", 0)) for x in wins)
        gross_loss = abs(sum(float(x.get("pnl", 0)) for x in losses))
        return {
            "initial_capital": self.initial_capital,
            "final_equity": self.final_equity,
            "pnl": self.pnl,
            "return_pct": round(self.return_pct, 10),
            "max_drawdown_pct": round(self.max_drawdown_pct, 10),
            "closed_trades": len(closes),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(len(wins) / len(closes) * 100, 10) if closes else 0.0,
            "profit_factor": gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0),
        }

class HistoricalBacktester:
    def __init__(self, capital: float = 1000.0, risk_pct: float = 0.5, fee_pct: float = 0.1, slippage_pct: float = 0.02, max_daily_loss_pct: float = 3.0):
        self.config = {"capital": float(capital), "risk_pct": float(risk_pct), "fee_pct": float(fee_pct), "slippage_pct": float(slippage_pct), "max_daily_loss_pct": float(max_daily_loss_pct)}

    @staticmethod
    def _ohlc(row: dict) -> tuple[float, float, float]:
        close = float(row["close"])
        high = float(row.get("high", close))
        low = float(row.get("low", close))
        if high <= 0 or low <= 0 or low > high or not low <= close <= high:
            raise ValueError("invalid candle high/low")
        return high, low, close

    @staticmethod
    def _exit_trigger(position, high: float, low: float) -> tuple[str, float] | None:
        if position.direction == "LONG":
            stop_hit, target_hit = low <= position.stop_price, high >= position.target_price
        else:
            stop_hit, target_hit = high >= position.stop_price, low <= position.target_price
        if stop_hit:
            return "SL", position.stop_price
        if target_hit:
            return "TP", position.target_price
        return None

    def run(self, candles: Iterable[dict], signal_provider: SignalProvider) -> BacktestResult:
        rows = [dict(candle) for candle in candles]
        account = PaperAccount(**self.config, cash=self.config["capital"])
        equity_curve: list[dict] = []
        previous_timestamp = None
        for row in rows:
            timestamp = str(row.get("timestamp") or row.get("time") or "")
            if previous_timestamp is not None and timestamp and timestamp < previous_timestamp:
                raise ValueError("candles must be ordered chronologically")
            previous_timestamp = timestamp or previous_timestamp
            high, low, close = self._ohlc(row)
            if account.position is not None:
                exit_event = self._exit_trigger(account.position, high, low)
                if exit_event is not None:
                    reason, trigger = exit_event
                    account.close_position(trigger, reason, timestamp or None, trigger_price=trigger)
            signal = signal_provider(row) or {}
            action = str(signal.get("action", "WAIT")).upper()
            if account.position is None and action in {"LONG", "SHORT"}:
                account.open_position(symbol=str(row.get("symbol", "BACKTEST")), direction=action, price=close, stop_distance=float(signal["stop_distance"]), rr=float(signal.get("rr", 2.0)), timestamp=timestamp or None)
            elif account.position is not None and action == "CLOSE":
                account.close_position(close, "SIGNAL", timestamp or None, trigger_price=close)
            equity_curve.append({"timestamp": timestamp, "equity": round(account.equity(close, str(row.get("symbol", "BACKTEST"))), 8)})
        if account.position is not None and rows:
            last = rows[-1]
            final_close = float(last["close"])
            account.close_position(final_close, "END", str(last.get("timestamp") or last.get("time") or "") or None, trigger_price=final_close)
            if equity_curve:
                equity_curve[-1]["equity"] = round(account.equity(), 8)
        return BacktestResult(initial_capital=self.config["capital"], final_equity=round(account.equity(), 8), trades=list(account.audit_log), equity_curve=equity_curve)
