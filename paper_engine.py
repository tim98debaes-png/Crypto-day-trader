"""Phase 5 paper-trading state engine.

Simulation only: this module never places exchange orders.
It turns validated strategy signals into a deterministic paper position,
with fees, slippage, risk sizing, daily loss protection and an audit log.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class PaperPosition:
    symbol: str
    direction: str
    entry_price: float
    quantity: float
    stop_price: float
    target_price: float
    opened_at: str
    entry_fee: float = 0.0


@dataclass
class PaperAccount:
    capital: float = 1000.0
    cash: float = 1000.0
    risk_pct: float = 0.5
    fee_pct: float = 0.1
    slippage_pct: float = 0.02
    max_daily_loss_pct: float = 3.0
    position: Optional[PaperPosition] = None
    day_start_equity: Optional[float] = None
    current_day: Optional[str] = None
    audit_log: list = field(default_factory=list)

    def __post_init__(self):
        if self.capital <= 0:
            raise ValueError("capital must be positive")
        if self.cash <= 0:
            self.cash = self.capital
        # A fresh account must measure its daily loss from its own allocated
        # capital.  Using the dataclass's old 1000 default for a 500-capital
        # portfolio account incorrectly looked like a 50% daily loss and
        # blocked the first trade.
        if self.day_start_equity is None:
            self.day_start_equity = self.cash
        if self.current_day is None:
            self.current_day = self._today()

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _roll_day(self, timestamp: Optional[str] = None) -> None:
        day = (timestamp or datetime.now(timezone.utc).isoformat())[:10]
        if day != self.current_day:
            self.current_day = day
            self.day_start_equity = self.equity()

    def equity(self, mark_price: Optional[float] = None) -> float:
        if self.position is None or mark_price is None:
            return float(self.cash)
        if self.position.direction == "LONG":
            unrealized = (mark_price - self.position.entry_price) * self.position.quantity
        else:
            unrealized = (self.position.entry_price - mark_price) * self.position.quantity
        return float(self.cash + unrealized)

    def daily_loss_pct(self, mark_price: Optional[float] = None) -> float:
        if self.day_start_equity is None or self.day_start_equity <= 0:
            return 100.0
        return (self.equity(mark_price) / self.day_start_equity - 1.0) * 100.0

    def can_open(self, mark_price: float) -> bool:
        return (
            self.position is None
            and self.daily_loss_pct(mark_price) > -self.max_daily_loss_pct
            and self.cash > 0
        )

    def open_position(
        self,
        symbol: str,
        direction: str,
        price: float,
        stop_distance: float,
        rr: float,
        timestamp: Optional[str] = None,
    ) -> PaperPosition:
        timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self._roll_day(timestamp)

        direction = direction.upper()
        if direction not in {"LONG", "SHORT"}:
            raise ValueError("direction must be LONG or SHORT")
        if price <= 0 or stop_distance <= 0 or rr <= 0:
            raise ValueError("price, stop_distance and rr must be positive")
        if not self.can_open(price):
            raise RuntimeError("paper account is not allowed to open a position")

        risk_amount = self.cash * self.risk_pct / 100.0
        quantity = risk_amount / stop_distance

        if direction == "LONG":
            entry = price * (1.0 + self.slippage_pct / 100.0)
            stop = entry - stop_distance
            target = entry + stop_distance * rr
        else:
            entry = price * (1.0 - self.slippage_pct / 100.0)
            stop = entry + stop_distance
            target = entry - stop_distance * rr

        entry_fee = entry * quantity * self.fee_pct / 100.0
        self.cash -= entry_fee

        self.position = PaperPosition(
            symbol=symbol,
            direction=direction,
            entry_price=entry,
            quantity=quantity,
            stop_price=stop,
            target_price=target,
            opened_at=timestamp,
            entry_fee=entry_fee,
        )
        self.audit_log.append({
            "event": "OPEN",
            "symbol": symbol,
            "direction": direction,
            "price": entry,
            "quantity": quantity,
            "entry_fee": entry_fee,
            "timestamp": timestamp,
        })
        return self.position

    def close_position(
        self,
        price: float,
        reason: str = "SIGNAL",
        timestamp: Optional[str] = None,
    ) -> float:
        if self.position is None:
            raise RuntimeError("no open paper position")
        if price <= 0:
            raise ValueError("price must be positive")

        timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        position = self.position

        if position.direction == "LONG":
            exit_price = price * (1.0 - self.slippage_pct / 100.0)
            gross = (exit_price - position.entry_price) * position.quantity
        else:
            exit_price = price * (1.0 + self.slippage_pct / 100.0)
            gross = (position.entry_price - exit_price) * position.quantity

        exit_fee = exit_price * position.quantity * self.fee_pct / 100.0
        pnl = gross - position.entry_fee - exit_fee
        self.cash += gross - exit_fee
        self.position = None

        self.audit_log.append({
            "event": "CLOSE",
            "symbol": position.symbol,
            "direction": position.direction,
            "price": exit_price,
            "quantity": position.quantity,
            "gross_pnl": gross,
            "entry_fee": position.entry_fee,
            "exit_fee": exit_fee,
            "pnl": pnl,
            "reason": reason,
            "timestamp": timestamp,
        })
        return float(pnl)

    def snapshot(self, mark_price: Optional[float] = None) -> dict:
        return {
            "cash": round(self.cash, 8),
            "equity": round(self.equity(mark_price), 8),
            "daily_loss_pct": round(self.daily_loss_pct(mark_price), 6),
            "position": None if self.position is None else {
                "symbol": self.position.symbol,
                "direction": self.position.direction,
                "entry_price": self.position.entry_price,
                "quantity": self.position.quantity,
                "stop_price": self.position.stop_price,
                "target_price": self.position.target_price,
            },
            "audit_events": len(self.audit_log),
        }
