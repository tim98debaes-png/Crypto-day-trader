"""Event-driven paper execution loop.

No exchange order calls are made here. Market snapshots are supplied by the
caller, making the engine deterministic and safe for paper trading.

Phase 20 rule: new paper entries are sourced from CandidateRegistry, not from
optimizer session state. The legacy ``candidate`` argument is retained only for
API compatibility and is never trusted for a new entry.
"""

from dataclasses import dataclass, field
from typing import Optional

from active_candidate_source import get_active_candidate
from candidate_registry import CandidateRegistry
from paper_engine import PaperAccount


@dataclass
class ExecutionStats:
    closed_trades: int = 0
    wins: int = 0
    losses: int = 0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    equity_curve: list = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return self.wins / self.closed_trades * 100 if self.closed_trades else 0.0

    @property
    def profit_factor(self) -> float:
        if self.gross_loss <= 0:
            return float("inf") if self.gross_profit > 0 else 0.0
        return self.gross_profit / self.gross_loss


class PaperExecutionLoop:
    def __init__(self, account: PaperAccount, registry: Optional[CandidateRegistry] = None):
        self.account = account
        self.registry = registry or CandidateRegistry()
        self.stats = ExecutionStats()

    def on_market(
        self,
        market: dict,
        candidate: Optional[dict] = None,
        exit_signal: bool = False,
    ) -> dict:
        price = float(market["price"])
        timestamp = market.get("timestamp")

        # Manage an existing position before looking for a new entry. Exits do
        # not require a currently active optimizer candidate.
        if self.account.position is not None:
            position = self.account.position
            stop_hit = (
                price <= position.stop_price if position.direction == "LONG"
                else price >= position.stop_price
            )
            target_hit = (
                price >= position.target_price if position.direction == "LONG"
                else price <= position.target_price
            )
            if stop_hit or target_hit or exit_signal:
                reason = "SL" if stop_hit else "TP" if target_hit else "SIGNAL"
                pnl = self.account.close_position(price, reason, timestamp)
                self._record_close(pnl)
                self._record_equity(price)
                return {"action": "CLOSE", "reason": reason, "pnl": pnl}

            self._record_equity(price)
            return {"action": "HOLD", "equity": self.account.equity(price)}

        # Phase 20: resolve the active candidate directly from the persistent
        # registry. The optimizer/session candidate passed by the caller is not
        # an authorization source for a new paper position.
        gate = get_active_candidate(self.registry, str(market["symbol"]))
        if not gate.allowed:
            self._record_equity(price)
            return {"action": "WAIT", "reason": gate.reason}

        active = dict(gate.active.candidate)
        direction = str(active.get("Direction", market.get("direction", "LONG"))).upper()
        requested_direction = str(market.get("direction", direction)).upper()
        if direction != requested_direction:
            self._record_equity(price)
            return {"action": "WAIT", "reason": "candidate_direction_mismatch"}

        rr_value = active.get("RR", active.get("rr", market.get("rr", 2.0)))
        try:
            rr = float(rr_value)
        except (TypeError, ValueError):
            rr = float(market.get("rr", 2.0))

        position = self.account.open_position(
            symbol=str(market["symbol"]),
            direction=direction,
            price=price,
            stop_distance=float(market["stop_distance"]),
            rr=rr,
            timestamp=timestamp,
        )
        self._record_equity(price)
        return {
            "action": "OPEN",
            "position": position,
            "candidate_id": gate.active.candidate_id,
        }

    def _record_close(self, pnl: float) -> None:
        self.stats.closed_trades += 1
        if pnl >= 0:
            self.stats.wins += 1
            self.stats.gross_profit += pnl
        else:
            self.stats.losses += 1
            self.stats.gross_loss += abs(pnl)

    def _record_equity(self, price: float) -> None:
        self.stats.equity_curve.append(self.account.equity(price))

    def summary(self) -> dict:
        curve = self.stats.equity_curve
        peak = curve[0] if curve else self.account.capital
        max_drawdown = 0.0
        for value in curve:
            peak = max(peak, value)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - value) / peak * 100)

        return {
            "equity": self.account.equity(),
            "closed_trades": self.stats.closed_trades,
            "wins": self.stats.wins,
            "losses": self.stats.losses,
            "win_rate_pct": self.stats.win_rate,
            "profit_factor": self.stats.profit_factor,
            "max_drawdown_pct": max_drawdown,
        }
