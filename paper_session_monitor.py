"""Fail-closed paper-session monitoring and safe candidate rollback.

Phase 21 is simulation-only. The monitor evaluates read-only paper-session
metrics and may switch the CandidateRegistry to an already registered,
previously promoted and still quality-approved candidate. It never creates,
promotes, or executes a new candidate and it never places live orders.
"""
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
        if self.min_closed_trades < 1:
            raise ValueError("min_closed_trades must be positive")
        if self.rollback_profit_factor >= self.watch_profit_factor:
            raise ValueError("rollback_profit_factor must be below watch threshold")
        if self.rollback_return_pct >= self.watch_return_pct:
            raise ValueError("rollback_return_pct must be below watch threshold")
        if self.rollback_drawdown_pct <= self.watch_drawdown_pct:
            raise ValueError("rollback_drawdown_pct must exceed watch threshold")
        if self.rollback_consecutive_losses <= self.watch_consecutive_losses:
            raise ValueError("rollback_consecutive_losses must exceed watch threshold")


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
        if value is None or value == "":
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            return number
    return None


def _loss_streak_from_events(events: list[dict[str, Any]]) -> int:
    streak = 0
    for event in reversed(events):
        if str(event.get("event", "")).upper() != "CLOSE":
            continue
        try:
            pnl = float(event.get("pnl", 0.0))
        except (TypeError, ValueError):
            continue
        if pnl < 0:
            streak += 1
        else:
            break
    return streak


def snapshot_from_account(account: Any, mark_price: float | None = None) -> dict[str, float]:
    """Build monitor metrics from the live-in-memory paper account."""
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
    # Account-level history is audit based. The portfolio adapter below uses
    # its tracked max drawdown when available; for an account we conservatively
    # use the larger realized loss from the audit trail and current loss.
    running = capital
    peak = capital
    max_dd = 0.0
    for event in closes:
        running += float(event.get("pnl", 0.0))
        peak = max(peak, running)
        if peak > 0:
            max_dd = max(max_dd, (peak - running) / peak * 100.0)
    if peak > 0:
        max_dd = max(max_dd, (peak - equity) / peak * 100.0)
    return {
        "closed_trades": float(len(closes)),
        "profit_factor": float(profit_factor),
        "return_pct": float(return_pct),
        "max_drawdown_pct": float(max_dd),
        "consecutive_losses": float(_loss_streak_from_events(events)),
    }


def snapshot_from_portfolio(portfolio: Any, marks: dict[str, Any] | None = None) -> dict[str, float]:
    """Build monitor metrics from the multi-asset paper portfolio summary."""
    marks = marks or {}
    summary = dict(portfolio.summary(marks))
    events = list(portfolio.audit_log())
    return {
        "closed_trades": float(summary.get("closed_trades", 0)),
        "profit_factor": float(summary.get("profit_factor", 0.0)),
        "return_pct": float(summary.get("return_pct", 0.0)),
        "max_drawdown_pct": float(summary.get("max_drawdown_pct", 0.0)),
        "consecutive_losses": float(_loss_streak_from_events(events)),
    }


def normalize_snapshot(snapshot: dict[str, Any]) -> dict[str, float] | None:
    if not isinstance(snapshot, dict):
        return None
    trades = _finite_number(snapshot, "closed_trades", "trades")
    profit_factor = _finite_number(snapshot, "profit_factor", "pf")
    return_pct = _finite_number(snapshot, "return_pct", "return")
    drawdown = _finite_number(snapshot, "max_drawdown_pct", "drawdown_pct", "drawdown")
    losses = _finite_number(snapshot, "consecutive_losses", "loss_streak")
    if any(value is None for value in (trades, profit_factor, return_pct, drawdown, losses)):
        return None
    if trades < 0 or profit_factor < 0 or drawdown < 0 or losses < 0:
        return None
    return {
        "closed_trades": float(trades),
        "profit_factor": float(profit_factor),
        "return_pct": float(return_pct),
        "max_drawdown_pct": float(drawdown),
        "consecutive_losses": float(int(losses)),
    }


class PaperSessionMonitor:
    """Monitor one active candidate and fail closed on unsafe state."""

    def __init__(self, registry: CandidateRegistry, thresholds: MonitorThresholds | None = None):
        self.registry = registry
        self.thresholds = thresholds or MonitorThresholds()

    def _record(self, decision: MonitorDecision) -> MonitorDecision:
        self.registry.record_monitor_event(decision)
        return decision

    def _safe_fallback(self, active_id: str) -> str | None:
        candidates = []
        for entry in self.registry.list_candidates():
            candidate_id = str(entry.get("id", ""))
            if not candidate_id or candidate_id == active_id:
                continue
            if str(entry.get("status", "")).upper() != "ROLLED_BACK":
                continue
            if not candidate_is_approved(dict(entry.get("candidate") or {})):
                continue
            candidates.append(entry)
        candidates.sort(
            key=lambda entry: (entry.get("promoted_at") or "", entry.get("created_at") or "", entry.get("id") or ""),
            reverse=True,
        )
        return str(candidates[0]["id"]) if candidates else None

    def evaluate(self, active_id: str | None, snapshot: dict[str, Any]) -> MonitorDecision:
        active = self.registry.active()
        if not active_id or active is None:
            return self._record(MonitorDecision(BLOCKED, "no_active_candidate", active_id, None, False))

        registry_active_id = str(active.get("id", ""))
        if registry_active_id != str(active_id):
            return self._record(MonitorDecision(BLOCKED, "active_candidate_changed", str(active_id), registry_active_id, False))
        if str(active.get("status", "")).upper() != "ACTIVE":
            return self._record(MonitorDecision(BLOCKED, "active_registry_status_invalid", registry_active_id, None, False))
        if not candidate_is_approved(dict(active.get("candidate") or {})):
            return self._record(MonitorDecision(BLOCKED, "active_candidate_quality_failed", registry_active_id, None, False))

        metrics = normalize_snapshot(snapshot)
        if metrics is None:
            return self._record(MonitorDecision(BLOCKED, "invalid_metrics", registry_active_id, None, False))
        if metrics["closed_trades"] < self.thresholds.min_closed_trades:
            return self._record(MonitorDecision(HEALTHY, "insufficient_sample", registry_active_id, None, True, metrics=metrics))

        watch_breaches: list[str] = []
        rollback_breaches: list[str] = []
        if metrics["profit_factor"] < self.thresholds.watch_profit_factor:
            watch_breaches.append("profit_factor")
        if metrics["profit_factor"] < self.thresholds.rollback_profit_factor:
            rollback_breaches.append("profit_factor")
        if metrics["return_pct"] < self.thresholds.watch_return_pct:
            watch_breaches.append("return")
        if metrics["return_pct"] < self.thresholds.rollback_return_pct:
            rollback_breaches.append("return")
        if metrics["max_drawdown_pct"] >= self.thresholds.watch_drawdown_pct:
            watch_breaches.append("drawdown")
        if metrics["max_drawdown_pct"] >= self.thresholds.rollback_drawdown_pct:
            rollback_breaches.append("drawdown")
        if metrics["consecutive_losses"] >= self.thresholds.watch_consecutive_losses:
            watch_breaches.append("loss_streak")
        if metrics["consecutive_losses"] >= self.thresholds.rollback_consecutive_losses:
            rollback_breaches.append("loss_streak")

        severe = (
            metrics["max_drawdown_pct"] >= self.thresholds.rollback_drawdown_pct
            or metrics["consecutive_losses"] >= self.thresholds.rollback_consecutive_losses
        )
        should_rollback = severe or len(rollback_breaches) >= 2
        if not should_rollback:
            status = WATCH if watch_breaches else HEALTHY
            reason = "degradation_watch" if watch_breaches else "within_thresholds"
            return self._record(MonitorDecision(status, reason, registry_active_id, None, True, tuple(sorted(set(watch_breaches))), metrics))

        target_id = self._safe_fallback(registry_active_id)
        if target_id is not None:
            restored = self.registry.rollback(target_id)
            if restored != target_id:
                return self._record(MonitorDecision(BLOCKED, "rollback_verification_failed", registry_active_id, target_id, False, tuple(sorted(set(rollback_breaches))), metrics))
            return self._record(MonitorDecision(ROLLBACK, "safe_fallback_restored", registry_active_id, target_id, True, tuple(sorted(set(rollback_breaches))), metrics))

        self.registry.deactivate()
        return self._record(MonitorDecision(BLOCKED, "no_safe_fallback", registry_active_id, None, False, tuple(sorted(set(rollback_breaches))), metrics))
