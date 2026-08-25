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
    """Conservative paper-performance rollback thresholds."""

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
    """Auditable result of one monitor evaluation."""

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


def _consecutive_losses(snapshot: dict[str, Any]) -> int | None:
    value = _finite_number(snapshot, "consecutive_losses", "loss_streak")
    if value is None or value < 0:
        return None
    return int(value)


def normalize_snapshot(snapshot: dict[str, Any]) -> dict[str, float] | None:
    """Normalize the minimum metrics needed for a safe monitoring decision."""
    if not isinstance(snapshot, dict):
        return None
    trades = _finite_number(snapshot, "closed_trades", "trades")
    profit_factor = _finite_number(snapshot, "profit_factor", "pf")
    return_pct = _finite_number(snapshot, "return_pct", "return")
    drawdown = _finite_number(snapshot, "max_drawdown_pct", "drawdown_pct", "drawdown")
    losses = _consecutive_losses(snapshot)
    if any(value is None for value in (trades, profit_factor, return_pct, drawdown, losses)):
        return None
    if trades < 0 or profit_factor < 0 or drawdown < 0:
        return None
    return {
        "closed_trades": float(trades),
        "profit_factor": float(profit_factor),
        "return_pct": float(return_pct),
        "max_drawdown_pct": float(drawdown),
        "consecutive_losses": float(losses),
    }


class PaperSessionMonitor:
    """Monitor one active candidate and fail closed on unsafe state."""

    def __init__(
        self,
        registry: CandidateRegistry,
        thresholds: MonitorThresholds | None = None,
    ):
        self.registry = registry
        self.thresholds = thresholds or MonitorThresholds()

    def _safe_fallback(self, active_id: str) -> str | None:
        candidates = []
        for entry in self.registry.list_candidates():
            candidate_id = str(entry.get("id", ""))
            if not candidate_id or candidate_id == active_id:
                continue
            if str(entry.get("status", "")).upper() != "ROLLED_BACK":
                continue
            candidate = dict(entry.get("candidate") or {})
            if not candidate_is_approved(candidate):
                continue
            candidates.append(entry)
        candidates.sort(
            key=lambda entry: (
                entry.get("promoted_at") or "",
                entry.get("created_at") or "",
                entry.get("id") or "",
            ),
            reverse=True,
        )
        return str(candidates[0]["id"]) if candidates else None

    def evaluate(self, active_id: str | None, snapshot: dict[str, Any]) -> MonitorDecision:
        """Evaluate metrics and perform only a safe, registry-backed rollback."""
        active = self.registry.active()
        if not active_id or active is None:
            decision = MonitorDecision(BLOCKED, "no_active_candidate", active_id, None, False)
            self.registry.record_monitor_event(decision)
            return decision

        registry_active_id = str(active.get("id", ""))
        if registry_active_id != str(active_id):
            decision = MonitorDecision(BLOCKED, "active_candidate_changed", str(active_id), registry_active_id, False)
            self.registry.record_monitor_event(decision)
            return decision

        if str(active.get("status", "")).upper() != "ACTIVE":
            decision = MonitorDecision(BLOCKED, "active_registry_status_invalid", registry_active_id, None, False)
            self.registry.record_monitor_event(decision)
            return decision

        if not candidate_is_approved(dict(active.get("candidate") or {})):
            decision = MonitorDecision(BLOCKED, "active_candidate_quality_failed", registry_active_id, None, False)
            self.registry.record_monitor_event(decision)
            return decision

        metrics = normalize_snapshot(snapshot)
        if metrics is None:
            decision = MonitorDecision(BLOCKED, "invalid_metrics", registry_active_id, None, False)
            self.registry.record_monitor_event(decision)
            return decision

        if metrics["closed_trades"] < self.thresholds.min_closed_trades:
            decision = MonitorDecision(
                HEALTHY,
                "insufficient_sample",
                registry_active_id,
                None,
                True,
                metrics=metrics,
            )
            self.registry.record_monitor_event(decision)
            return decision

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

        # Require two independent rollback signals. A severe drawdown or loss
        # streak is independently sufficient because it represents a hard risk
        # boundary rather than ordinary statistical noise.
        severe = (
            metrics["max_drawdown_pct"] >= self.thresholds.rollback_drawdown_pct
            or metrics["consecutive_losses"] >= self.thresholds.rollback_consecutive_losses
        )
        should_rollback = severe or len(rollback_breaches) >= 2

        if not should_rollback:
            status = WATCH if watch_breaches else HEALTHY
            reason = "degradation_watch" if watch_breaches else "within_thresholds"
            decision = MonitorDecision(
                status,
                reason,
                registry_active_id,
                None,
                True,
                tuple(sorted(set(watch_breaches))),
                metrics,
            )
            self.registry.record_monitor_event(decision)
            return decision

        target_id = self._safe_fallback(registry_active_id)
        if target_id is not None:
            restored = self.registry.rollback(target_id)
            if restored != target_id:
                decision = MonitorDecision(
                    BLOCKED,
                    "rollback_verification_failed",
                    registry_active_id,
                    target_id,
                    False,
                    tuple(sorted(set(rollback_breaches))),
                    metrics,
                )
                self.registry.record_monitor_event(decision)
                return decision
            decision = MonitorDecision(
                ROLLBACK,
                "safe_fallback_restored",
                registry_active_id,
                target_id,
                True,
                tuple(sorted(set(rollback_breaches))),
                metrics,
            )
            self.registry.record_monitor_event(decision)
            return decision

        # No previously approved fallback exists. Deactivate the active
        # candidate so the execution boundary sees no active candidate and
        # therefore fails closed for new entries.
        self.registry.deactivate()
        decision = MonitorDecision(
            BLOCKED,
            "no_safe_fallback",
            registry_active_id,
            None,
            False,
            tuple(sorted(set(rollback_breaches))),
            metrics,
        )
        self.registry.record_monitor_event(decision)
        return decision
