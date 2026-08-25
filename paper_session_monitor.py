"""Fail-closed paper-session monitoring and safe candidate rollback."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from candidate_registry import CandidateRegistry
from paper_router import candidate_is_approved

SCHEMA_VERSION = 1
HEALTHY = "HEALTHY"
WATCH = "WATCH"
ROLLBACK = "ROLLBACK"
BLOCKED = "BLOCKED"

@dataclass(frozen=True)
class MonitorThresholds:
    min_closed_trades: int = 20
    watch_profit_factor: float = 1.20
    rollback_profit_factor: float = 1.00
    watch_return_pct: float = 0.0
    rollback_return_pct: float = -5.0
    watch_drawdown_pct: float = 15.0
    rollback_drawdown_pct: float = 20.0
    watch_consecutive_losses: int = 4
    rollback_consecutive_losses: int = 6

    def __post_init__(self):
        if self.min_closed_trades < 1: raise ValueError("min_closed_trades must be positive")
        if self.rollback_profit_factor >= self.watch_profit_factor: raise ValueError("rollback_profit_factor must be below watch threshold")
        if self.rollback_return_pct >= self.watch_return_pct: raise ValueError("rollback_return_pct must be below watch threshold")
        if self.rollback_drawdown_pct <= self.watch_drawdown_pct: raise ValueError("rollback_drawdown_pct must exceed watch threshold")
        if self.rollback_consecutive_losses <= self.watch_consecutive_losses: raise ValueError("rollback_consecutive_losses must exceed watch threshold")

@dataclass(frozen=True)
class MonitorDecision:
    status: str
    reason: str
    active_id: str | None
    target_id: str | None
    allow_new_entries: bool
    breaches: tuple[str, ...] = ()
    metrics: dict[str, float] | None = None
    schema_version: int = SCHEMA_VERSION

def _finite_number(snapshot: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = snapshot.get(key)
        if value is None or value == "": continue
        try: number = float(value)
        except (TypeError, ValueError): continue
        if math.isfinite(number): return number
    return None

def _loss_streak_from_events(events: list[dict[str, Any]]) -> int:
    streak = 0
    for event in reversed(events):
        if str(event.get("event", "")).upper() != "CLOSE": continue
        try: pnl = float(event.get("pnl", 0.0))
        except (TypeError, ValueError): continue
        if pnl < 0: streak += 1
        else: break
    return streak

def snapshot_from_account(account: Any, mark_price: float | None = None) -> dict[str, float]:
    events = list(getattr(account, "audit_log", []) or [])
    closes = [event for event in events if str(event.get("event", "")).upper() == "CLOSE"]
    wins = [event for event in closes if float(event.get("pnl", 0.0)) > 0]
    losses = [event for event in closes if float(event.get("pnl", 0.0)) < 0]
    gross_profit = sum(float(event.get("pnl", 0.0)) for event in wins)
    gross_loss = abs(sum(float(event.get("pnl", 0.0)) for event in losses))
    profit_factor = gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0)
    equity = float(account.equity(mark_price))
    capital = float(getattr(account, "capital", equity))
    return_pct = (equity / capital - 1.0) * 100.0 if capital > 0 else -100.0
    running, peak, max_dd = capital, capital, 0.0
    for event in closes:
        running += float(event.get("pnl", 0.0)); peak = max(peak, running)
        if peak > 0: max_dd = max(max_dd, (peak - running) / peak * 100.0)
    if peak > 0: max_dd = max(max_dd, (peak - equity) / peak * 100.0)
    return {"closed_trades": float(len(closes)), "profit_factor": float(profit_factor), "return_pct": float(return_pct), "max_drawdown_pct": float(max_dd), "consecutive_losses": float(_loss_streak_from_events(events))}

def snapshot_from_portfolio(portfolio: Any, marks: dict[str, Any] | None = None) -> dict[str, float]:
    summary = dict(portfolio.summary(marks or {})); events = list(portfolio.audit_log())
    return {"closed_trades": float(summary.get("closed_trades", 0)), "profit_factor": float(summary.get("profit_factor", 0.0)), "return_pct": float(summary.get("return_pct", 0.0)), "max_drawdown_pct": float(summary.get("max_drawdown_pct", 0.0)), "consecutive_losses": float(_loss_streak_from_events(events))}

def normalize_snapshot(snapshot: dict[str, Any]) -> dict[str, float] | None:
    if not isinstance(snapshot, dict): return None
    values = [_finite_number(snapshot, "closed_trades", "trades"), _finite_number(snapshot, "profit_factor", "pf"), _finite_number(snapshot, "return_pct", "return"), _finite_number(snapshot, "max_drawdown_pct", "drawdown_pct", "drawdown"), _finite_number(snapshot, "consecutive_losses", "loss_streak")]
    if any(value is None for value in values): return None
    trades, pf, ret, dd, losses = values
    if trades < 0 or pf < 0 or dd < 0 or losses < 0: return None
    return {"closed_trades": float(trades), "profit_factor": float(pf), "return_pct": float(ret), "max_drawdown_pct": float(dd), "consecutive_losses": float(int(losses))}

class PaperSessionMonitor:
    def __init__(self, registry: CandidateRegistry, thresholds: MonitorThresholds | None = None):
        self.registry = registry; self.thresholds = thresholds or MonitorThresholds()

    def _record(self, decision: MonitorDecision) -> MonitorDecision:
        self.registry.record_monitor_event(decision); return decision

    def _safe_fallback(self, active_id: str) -> str | None:
        candidates = []
        for entry in self.registry.list_candidates():
            candidate_id = str(entry.get("id", ""))
            if not candidate_id or candidate_id == active_id: continue
            if str(entry.get("status", "")).upper() not in {"ROLLED_BACK", "ACTIVE"}: continue
            if not candidate_is_approved(dict(entry.get("candidate") or {})): continue
            candidates.append(entry)
        candidates.sort(key=lambda e: (e.get("promoted_at") or "", e.get("created_at") or "", e.get("id") or ""), reverse=True)
        return str(candidates[0]["id"]) if candidates else None

    def evaluate(self, active_id: str | None, snapshot: dict[str, Any]) -> MonitorDecision:
        active = self.registry.active()
        if not active_id or active is None: return self._record(MonitorDecision(BLOCKED, "no_active_candidate", active_id, None, False))
        registry_active_id = str(active.get("id", ""))
        if registry_active_id != str(active_id): return self._record(MonitorDecision(BLOCKED, "active_candidate_changed", str(active_id), registry_active_id, False))
        if str(active.get("status", "")).upper() != "ACTIVE": return self._record(MonitorDecision(BLOCKED, "active_registry_status_invalid", registry_active_id, None, False))
        if not candidate_is_approved(dict(active.get("candidate") or {})): return self._record(MonitorDecision(BLOCKED, "active_candidate_quality_failed", registry_active_id, None, False))
        metrics = normalize_snapshot(snapshot)
        if metrics is None: return self._record(MonitorDecision(BLOCKED, "invalid_metrics", registry_active_id, None, False))
        if metrics["closed_trades"] < self.thresholds.min_closed_trades: return self._record(MonitorDecision(HEALTHY, "insufficient_sample", registry_active_id, None, True, metrics=metrics))
        watch, rollback = [], []
        if metrics["profit_factor"] < self.thresholds.watch_profit_factor: watch.append("profit_factor")
        if metrics["profit_factor"] < self.thresholds.rollback_profit_factor: rollback.append("profit_factor")
        if metrics["return_pct"] < self.thresholds.watch_return_pct: watch.append("return")
        if metrics["return_pct"] < self.thresholds.rollback_return_pct: rollback.append("return")
        if metrics["max_drawdown_pct"] >= self.thresholds.watch_drawdown_pct: watch.append("drawdown")
        if metrics["max_drawdown_pct"] >= self.thresholds.rollback_drawdown_pct: rollback.append("drawdown")
        if metrics["consecutive_losses"] >= self.thresholds.watch_consecutive_losses: watch.append("loss_streak")
        if metrics["consecutive_losses"] >= self.thresholds.rollback_consecutive_losses: rollback.append("loss_streak")
        severe = metrics["max_drawdown_pct"] >= self.thresholds.rollback_drawdown_pct or metrics["consecutive_losses"] >= self.thresholds.rollback_consecutive_losses
        if not (severe or len(rollback) >= 2):
            return self._record(MonitorDecision(WATCH if watch else HEALTHY, "degradation_watch" if watch else "within_thresholds", registry_active_id, None, True, tuple(sorted(set(watch))), metrics))
        target_id = self._safe_fallback(registry_active_id)
        if target_id is not None:
            restored = self.registry.rollback(target_id)
            if restored != target_id: return self._record(MonitorDecision(BLOCKED, "rollback_verification_failed", registry_active_id, target_id, False, tuple(sorted(set(rollback))), metrics))
            return self._record(MonitorDecision(ROLLBACK, "safe_fallback_restored", registry_active_id, target_id, False, tuple(sorted(set(rollback))), metrics))
        self.registry.deactivate()
        return self._record(MonitorDecision(BLOCKED, "no_safe_fallback", registry_active_id, None, False, tuple(sorted(set(rollback)),), metrics))
