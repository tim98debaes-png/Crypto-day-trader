"""Event-driven paper execution loop with portfolio-safe exits."""
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
    def win_rate(self) -> float: return self.wins / self.closed_trades * 100 if self.closed_trades else 0.0
    @property
    def profit_factor(self) -> float:
        if self.gross_loss <= 0: return float("inf") if self.gross_profit > 0 else 0.0
        return self.gross_profit / self.gross_loss

class PaperExecutionLoop:
    def __init__(self, account: PaperAccount, registry: Optional[CandidateRegistry] = None,
                 monitor: Optional[PaperSessionMonitor] = None, observer: Optional[PaperSessionObserver] = None,
                 persist_observability: bool = False):
        self.account = account; self._registry_explicit = registry is not None; self.registry = registry or CandidateRegistry()
        self.monitor = monitor or PaperSessionMonitor(self.registry); self._observer_tmpdir = None
        if observer is not None: self.observer = observer
        elif persist_observability: self.observer = PaperSessionObserver()
        else:
            self._observer_tmpdir = tempfile.TemporaryDirectory(prefix="paper-observer-")
            self.observer = PaperSessionObserver(state_path=f"{self._observer_tmpdir.name}/session.json")
        self.stats = ExecutionStats(); self.last_monitor_decision = None

    def _monitor_before_entry(self, mark_price: float):
        active = self.registry.active(); active_id = str(active.get("id")) if active else None
        self.last_monitor_decision = self.monitor.evaluate(active_id, snapshot_from_account(self.account, mark_price)) if active_id else self.monitor.evaluate(None, {})
        return self.last_monitor_decision

    def _heartbeat(self, mark_price: float, timestamp: Optional[str] = None) -> None:
        summary = self.summary(_observe=False, mark_price=mark_price); active = self.registry.active()
        self.observer.heartbeat(summary, active_candidate_id=str(active.get("id")) if active else None, timestamp=timestamp)

    def on_market(self, market: dict, candidate: Optional[dict] = None, exit_signal: bool = False) -> dict:
        symbol = str(market["symbol"]).upper(); price = float(market["price"]); timestamp = market.get("timestamp")
        self.account.equity(price, symbol)
        position = self.account.positions.get(symbol)
        if position is not None:
            atr_distance = float(market.get("atr_distance", position.initial_stop_distance / 3.0))
            risk_distance = position.initial_stop_distance
            reward_hit = (price >= position.entry_price + risk_distance * self.account.risk_config.partial_take_profit_r
                          if position.direction == "LONG" else price <= position.entry_price - risk_distance * self.account.risk_config.partial_take_profit_r)
            actions = []
            if reward_hit and not position.partial_taken:
                partial_pnl = self.account.take_partial_profit(symbol, price, timestamp)
                actions.append({"action":"PARTIAL_CLOSE","symbol":symbol,"pnl":partial_pnl})
            if position.partial_taken:
                self.account.update_trailing_stop(symbol, price, atr_distance)
            stop_hit = price <= position.stop_price if position.direction == "LONG" else price >= position.stop_price
            target_hit = price >= position.target_price if position.direction == "LONG" else price <= position.target_price
            time_stop = self.account.position_age_minutes(symbol, timestamp) >= self.account.risk_config.time_stop_minutes
            if stop_hit or target_hit or exit_signal or time_stop:
                reason = "SL" if stop_hit else "TP" if target_hit else "TIME_STOP" if time_stop else "SIGNAL"
                # A sampled market price can jump through a stop/target between
                # polling intervals. Execute the deterministic paper fill at the
                # trigger price rather than the later sample; this prevents a
                # sampling artifact from turning 0.5% intended risk into a much
                # larger loss (as observed in run #72).
                trigger_price = position.stop_price if stop_hit else position.target_price if target_hit else price
                fill_price = trigger_price if reason in {"SL", "TP"} else price
                pnl = self.account.close_position(fill_price, reason, timestamp, symbol=symbol, trigger_price=trigger_price)
                self._record_close(pnl); self._record_equity(fill_price, symbol)
                result = {"action":"CLOSE","symbol":symbol,"reason":reason,"pnl":pnl,"trigger_price":trigger_price,"fill_price":fill_price,"pre_actions":actions}; self._heartbeat(fill_price,timestamp); return result
            self._record_equity(price, symbol)
            result = {"action":actions[0]["action"] if actions else "HOLD","symbol":symbol,"equity":self.account.equity()}
            if actions: result["pnl"] = actions[0]["pnl"]
            self._heartbeat(price,timestamp); return result

        registry_active = self.registry.active()
        if registry_active is None:
            if self._registry_explicit or not candidate_is_approved(candidate or {}):
                self._record_equity(price,symbol); result={"action":"WAIT","reason":"no_active_candidate"}; self._heartbeat(price,timestamp); return result
            active_candidate=dict(candidate); candidate_id=None
        else:
            decision=self._monitor_before_entry(price)
            if str(decision.status).upper()=="ROLLBACK":
                self._record_equity(price,symbol); result={"action":"WAIT","reason":"paper_monitor_rollback_recovery","monitor_status":"BLOCKED","monitor_reason":decision.reason}; self._heartbeat(price,timestamp); return result
            if not decision.allow_new_entries:
                self._record_equity(price,symbol); result={"action":"WAIT","reason":"paper_monitor_blocked","monitor_status":decision.status,"monitor_reason":decision.reason}; self._heartbeat(price,timestamp); return result
            gate=get_active_candidate(self.registry,symbol)
            if not gate.allowed:
                self._record_equity(price,symbol); result={"action":"WAIT","reason":gate.reason}; self._heartbeat(price,timestamp); return result
            active_candidate=dict(gate.active.candidate); candidate_id=gate.active.candidate_id
        requested_direction=str(market.get("direction", active_candidate.get("Direction", "LONG"))).upper()
        candidate_direction=str(active_candidate.get("Direction", requested_direction)).upper()
        if candidate_direction in {"BOTH", "ANY", "PORTFOLIO"}:
            direction=requested_direction
        else:
            direction=candidate_direction
            if direction != requested_direction:
                self._record_equity(price,symbol); result={"action":"WAIT","reason":"candidate_direction_mismatch"}; self._heartbeat(price,timestamp); return result
        try: rr=float(active_candidate.get("RR",active_candidate.get("rr",market.get("rr",2.0))))
        except (TypeError,ValueError): rr=float(market.get("rr",2.0))
        try:
            position=self.account.open_position(symbol=symbol,direction=direction,price=price,stop_distance=float(market["stop_distance"]),rr=rr,timestamp=timestamp,risk_pct_override=market.get("risk_pct_override"),strategy_score=market.get("strategy_score"),strategy_tier=market.get("strategy_tier"))
        except RuntimeError as exc:
            self._record_equity(price,symbol); result={"action":"WAIT","reason":"risk_control_block","detail":str(exc)}; self._heartbeat(price,timestamp); return result
        self._record_equity(price,symbol); result={"action":"OPEN","position":position,"candidate_id":candidate_id,"monitor_status":getattr(locals().get("decision",None),"status","HEALTHY"),"open_position_count":len(self.account.positions)}; self._heartbeat(price,timestamp); return result

    def _record_close(self,pnl:float)->None:
        self.stats.closed_trades+=1
        if pnl>=0: self.stats.wins+=1; self.stats.gross_profit+=pnl
        else: self.stats.losses+=1; self.stats.gross_loss+=abs(pnl)

    def _record_equity(self,price:float,symbol:str)->None: self.stats.equity_curve.append(self.account.equity(price,symbol))

    def summary(self,*,_observe:bool=True,mark_price:Optional[float]=None)->dict:
        curve=self.stats.equity_curve; peak=curve[0] if curve else self.account.capital; max_drawdown=0.0
        for value in curve:
            peak=max(peak,value)
            if peak>0: max_drawdown=max(max_drawdown,(peak-value)/peak*100)
        result={"equity":self.account.equity(mark_price),"closed_trades":self.stats.closed_trades,"wins":self.stats.wins,"losses":self.stats.losses,"win_rate_pct":self.stats.win_rate,"profit_factor":self.stats.profit_factor,"return_pct":(self.account.equity(mark_price)/self.account.capital-1.0)*100.0,"max_drawdown_pct":max_drawdown,"open_positions":len(self.account.positions),"open_symbols":sorted(self.account.positions.keys()),"open_risk_pct":self.account.open_risk_pct(),"loss_streak":self.account.loss_streak,"cooldown_until":self.account.cooldown_until,"symbol_cooldowns":dict(self.account.symbol_cooldown_until),"monitor_status":getattr(self.last_monitor_decision,"status",None),"monitor_reason":getattr(self.last_monitor_decision,"reason",None),"monitor_breaches":list(getattr(self.last_monitor_decision,"breaches",()) or ())}
        if _observe: self._heartbeat(mark_price or self.account.equity(),None)
        return result
