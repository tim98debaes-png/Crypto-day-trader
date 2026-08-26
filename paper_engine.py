"""Phase 5 paper-trading portfolio state engine.

Simulation only: this module never places exchange orders.
It turns validated strategy signals into deterministic paper positions,
with fees, slippage, research risk sizing, daily loss protection, runtime
safety and an audit log. The research portfolio has no artificial
position-count cap; each symbol is limited to one open position.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from phase34_runtime_guard import evaluate_entry_guard


# Phase 3 research risk: deliberately unchanged at 0.5% of available cash per
# position. We broaden candidate acceptance, but do not compensate by taking
# larger risk per trade. Daily loss protection remains 3%.
RESEARCH_RISK_PCT = 0.5
RESEARCH_MAX_DAILY_LOSS_PCT = 3.0


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
    risk_pct: float = RESEARCH_RISK_PCT
    fee_pct: float = 0.1
    slippage_pct: float = 0.02
    max_daily_loss_pct: float = RESEARCH_MAX_DAILY_LOSS_PCT
    positions: dict[str, PaperPosition] = field(default_factory=dict)
    last_prices: dict[str, float] = field(default_factory=dict)
    day_start_equity: Optional[float] = None
    current_day: Optional[str] = None
    audit_log: list = field(default_factory=list)

    def __post_init__(self):
        if self.capital <= 0:
            raise ValueError("capital must be positive")
        if self.cash <= 0:
            self.cash = self.capital
        if self.risk_pct <= 0:
            raise ValueError("risk_pct must be positive")
        if self.max_daily_loss_pct <= 0:
            raise ValueError("max_daily_loss_pct must be positive")
        if self.day_start_equity is None:
            self.day_start_equity = self.capital
        if self.current_day is None:
            self.current_day = self._today()

    @property
    def position(self) -> Optional[PaperPosition]:
        """Backward-compatible view of the first open position."""
        return next(iter(self.positions.values()), None)

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _roll_day(self, timestamp: Optional[str] = None) -> None:
        day = (timestamp or datetime.now(timezone.utc).isoformat())[:10]
        if day != self.current_day:
            self.current_day = day
            self.day_start_equity = self.equity()

    def has_position(self, symbol: str) -> bool:
        return str(symbol) in self.positions

    def equity(self, mark_price: Optional[float] = None, symbol: Optional[str] = None) -> float:
        if mark_price is not None and symbol is not None:
            self.last_prices[str(symbol)] = float(mark_price)
        unrealized = 0.0
        for position in self.positions.values():
            price = self.last_prices.get(position.symbol)
            if price is None:
                continue
            if position.direction == "LONG":
                unrealized += (price - position.entry_price) * position.quantity
            else:
                unrealized += (position.entry_price - price) * position.quantity
        return float(self.cash + unrealized)

    def daily_loss_pct(self, mark_price: Optional[float] = None, symbol: Optional[str] = None) -> float:
        if self.day_start_equity is None or self.day_start_equity <= 0:
            return 100.0
        return (self.equity(mark_price, symbol) / self.day_start_equity - 1.0) * 100.0

    def can_open(self, mark_price: float, symbol: str) -> bool:
        return (
            not self.has_position(symbol)
            and self.daily_loss_pct(mark_price, symbol) > -self.max_daily_loss_pct
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
        *,
        strategy_ready: bool = True,
        heartbeat_age_seconds: float | None = 0.0,
        paper_mode: bool = True,
    ) -> PaperPosition:
        """Open one position for a symbol; no artificial portfolio cap."""
        timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self._roll_day(timestamp)
        symbol = str(symbol)
        direction = direction.upper()
        if direction not in {"LONG", "SHORT"}:
            raise ValueError("direction must be LONG or SHORT")
        if price <= 0 or stop_distance <= 0 or rr <= 0:
            raise ValueError("price, stop_distance and rr must be positive")
        if self.has_position(symbol):
            raise RuntimeError(f"paper account already has an open position for {symbol}")

        guard = evaluate_entry_guard(
            paper_mode=paper_mode,
            strategy_ready=strategy_ready,
            heartbeat_age_seconds=heartbeat_age_seconds,
            drawdown_pct=self.daily_loss_pct(price, symbol),
            max_drawdown_pct=20.0,
        )
        if not guard.allowed:
            raise RuntimeError(
                "paper account is not allowed to open a position: "
                + ",".join(guard.reasons)
            )
        if not self.can_open(price, symbol):
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
        self.last_prices[symbol] = float(price)
        position = PaperPosition(symbol, direction, entry, quantity, stop, target, timestamp, entry_fee)
        self.positions[symbol] = position
        self.audit_log.append({
            "event": "OPEN", "symbol": symbol, "direction": direction,
            "price": entry, "quantity": quantity, "entry_fee": entry_fee,
            "timestamp": timestamp,
        })
        return position

    def close_position(
        self,
        price: float,
        reason: str = "SIGNAL",
        timestamp: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> float:
        if symbol is None:
            position = self.position
            if position is None:
                raise RuntimeError("no open paper position")
            symbol = position.symbol
        else:
            symbol = str(symbol)
            position = self.positions.get(symbol)
            if position is None:
                raise RuntimeError(f"no open paper position for {symbol}")
        if price <= 0:
            raise ValueError("price must be positive")
        timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.last_prices[symbol] = float(price)
        if position.direction == "LONG":
            exit_price = price * (1.0 - self.slippage_pct / 100.0)
            gross = (exit_price - position.entry_price) * position.quantity
        else:
            exit_price = price * (1.0 + self.slippage_pct / 100.0)
            gross = (position.entry_price - exit_price) * position.quantity
        exit_fee = exit_price * position.quantity * self.fee_pct / 100.0
        pnl = gross - position.entry_fee - exit_fee
        self.cash += gross - exit_fee
        del self.positions[symbol]
        self.audit_log.append({
            "event": "CLOSE", "symbol": symbol, "direction": position.direction,
            "price": exit_price, "quantity": position.quantity,
            "gross_pnl": gross, "entry_fee": position.entry_fee,
            "exit_fee": exit_fee, "pnl": pnl, "reason": reason,
            "timestamp": timestamp,
        })
        return float(pnl)

    def snapshot(self, mark_price: Optional[float] = None, symbol: Optional[str] = None) -> dict:
        return {
            "cash": round(self.cash, 8),
            "equity": round(self.equity(mark_price, symbol), 8),
            "daily_loss_pct": round(self.daily_loss_pct(), 6),
            "positions": [
                {
                    "symbol": p.symbol, "direction": p.direction,
                    "entry_price": p.entry_price, "quantity": p.quantity,
                    "stop_price": p.stop_price, "target_price": p.target_price,
                }
                for p in self.positions.values()
            ],
            "position_count": len(self.positions),
            "audit_events": len(self.audit_log),
        }
