"""Event-driven paper execution loop."""

from dataclasses import dataclass, field
from typing import Optional
import tempfile

from active_candidate_source import get_active_candidate
from candidate_registry import CandidateRegistry
from paper_engine import PaperAccount
from paper_router import candidate_is_approved
from paper_session_monitor import PaperSessionMonitor, snapshot_from_account
from paper_session_observability import PaperSessionObserver

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
    def __init__(self, account: PaperAccount, registry: Optional[CandidateRegistry] = None,
                 monitor: Optional[PaperSessionMonitor] = None,
                 observer: Optional[PaperSessionObserver] = None,
                 persist_observability: bool = False):
        self.account = account
        self.registry = registry or CandidateRegistry()
        self.monitor = monitor or PaperSessionMonitor(self.registry)
        self._observer_tmpdir = None
        if observer is not None:
            self.observer = observer
        elif persist_observability:
            self.observer = PaperSessionObserver()
        else:
            self._observer_tmpdir = tempfile.TemporaryDirectory(prefix="paper-observer-")
            self.observer = PaperSessionObserver(state_path=f"{self._observer_tmpdir.name}/session.json")
        self.stats = ExecutionStats()
        self.last_monitor_decision = None

    def _monitor_before_entry(self, mark_price: float):
        active = self.registry.active()
        active_id = str(active.get("id")) if active else None
        self.last_monitor_decision = self.monitor.evaluate(active_id, snapshot_from_account(self.account, mark_price)) if active_id else self.monitor.evaluate(None, {})
        return self.last_monitor_decision

    def _heartbeat(self, mark_price: float, timestamp: Optional[str] = None) -> None:
        summary = self.summary(_observe=False, mark_price=mark_price)
        active = self.registry.active()
        self.observer.heartbeat(summary, active_candidate_id=str(active.get("id")) if active else None, timestamp=timestamp)

    def on_market(self, market: dict, candidate: Optional[dict] = None, exit_signal: bool = False) -> dict:
        price = float(market["price"])
        timestamp = market.get("timestamp")
        if self.account.position is not None:
            position = self.account.position
            stop_hit = price <= position.stop_price if position.direction == "LONG" else price >= position.stop_price
            target_hit = price >= position.target_price if position.direction == "LONG" else price <= position.target_price
            if stop_hit or target_hit or exit_signal:
                reason = "SL" if stop_hit else "TP" if target_hit else "SIGNAL"
                pnl = self.account.close_position(price, reason, timestamp)
                self._record_close(pnl)
                self._record_equity(price)
                result = {"action": "CLOSE", "reason": reason, "pnl": pnl}
                self._heartbeat(price, timestamp)
                return result
            self._record_equity(price)
            result = {"action": "HOLD", "equity": self.account.equity(price)}
            self._heartbeat(price, timestamp)
            return result

        registry_active = self.registry.active()
        # Explicit candidates are supported for isolated paper simulations and
        # legacy callers; the persistent registry remains authoritative whenever
        # an active rollout exists.
        if registry_active is None and candidate is not None:
            if not candidate_is_approved(candidate):
                self._record_equity(price)
                result = {"action": "WAIT", "reason": "candidate_not_approved"}
                self._heartbeat(price, timestamp)
                return result
            active_candidate = dict(candidate)
            candidate_id = None
            decision = None
        elif registry_active is None:
            decision = self._monitor_before_entry(price)
            self._record_equity(price)
            result = {"action": "WAIT", "reason": decision.reason, "monitor_status": decision.status, "monitor_reason": decision.reason}
            self._heartbeat(price, timestamp)
            return result
        else:
            decision = self._monitor_before_entry(price)
            if str(decision.status).upper() == "ROLLBACK":
                self._record_equity(price)
                result = {"action": "WAIT", "reason": "paper_monitor_rollback_recovery", "monitor_status": "BLOCKED", "monitor_reason": decision.reason}
                self._heartbeat(price, timestamp)
                return result
            if not decision.allow_new_entries:
                self._record_equity(price)
                result = {"action": "WAIT", "reason": "paper_monitor_blocked", "monitor_status": decision.status, "monitor_reason": decision.reason}
                self._heartbeat(price, timestamp)
                return result
            gate = get_active_candidate(self.registry, str(market["symbol"]))
            if not gate.allowed:
                self._record_equity(price)
                result = {"action": "WAIT", "reason": gate.reason}
                self._heartbeat(price, timestamp)
                return result
            active_candidate = dict(gate.active.candidate)
            candidate_id = gate.active.candidate_id

        direction = str(active_candidate.get("Direction", market.get("direction", "LONG"))).upper()
        requested_direction = str(market.get("direction", direction)).upper()
        if direction != requested_direction:
            self._record_equity(price)
            result = {"action": "WAIT", "reason": "candidate_direction_mismatch"}
            self._heartbeat(price, timestamp)
            return result
        try:
            rr = float(active_candidate.get("RR", active_candidate.get("rr", market.get("rr", 2.0))))
        except (TypeError, ValueError):
            rr = float(market.get("rr", 2.0))
        position = self.account.open_position(symbol=str(market["symbol"]), direction=direction, price=price, stop_distance=float(market["stop_distance"]), rr=rr, timestamp=timestamp)
        self._record_equity(price)
        result = {"action": "OPEN", "position": position, "candidate_id": candidate_id, "monitor_status": getattr(decision, "status", "HEALTHY")}
        self._heartbeat(price, timestamp)
        return result

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

    def summary(self, *, _observe: bool = True, mark_price: Optional[float] = None) -> dict:
        curve = self.stats.equity_curve
        peak = curve[0] if curve else self.account.capital
        max_drawdown = 0.0
        for value in curve:
            peak = max(peak, value)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - value) / peak * 100)
        result = {"equity": self.account.equity(mark_price), "closed_trades": self.stats.closed_trades, "wins": self.stats.wins, "losses": self.stats.losses, "win_rate_pct": self.stats.win_rate, "profit_factor": self.stats.profit_factor, "return_pct": (self.account.equity(mark_price) / self.account.capital - 1.0) * 100.0, "max_drawdown_pct": max_drawdown, "open_positions": int(self.account.position is not None), "monitor_status": getattr(self.last_monitor_decision, "status", None), "monitor_reason": getattr(self.last_monitor_decision, "reason", None), "monitor_breaches": list(getattr(self.last_monitor_decision, "breaches", ()) or ())}
        if _observe:
            self._heartbeat(mark_price or self.account.equity(), None)
        return result
