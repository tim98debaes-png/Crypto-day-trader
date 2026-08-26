"""Phase 34 paper-trading runtime safety guard.

This module is deliberately paper-only. It provides a deterministic decision
boundary for new entries without placing orders or mutating portfolio state.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeGuardDecision:
    allowed: bool
    reasons: tuple[str, ...]


def evaluate_entry_guard(
    *,
    paper_mode: bool,
    strategy_ready: bool,
    heartbeat_age_seconds: float | None,
    max_heartbeat_age_seconds: float = 300.0,
    drawdown_pct: float = 0.0,
    max_drawdown_pct: float = 20.0,
) -> RuntimeGuardDecision:
    """Return whether a new paper entry is allowed.

    The guard fails closed: missing/stale operational state, an unready
    strategy, non-paper mode, or excessive drawdown blocks a new entry.
    """
    reasons: list[str] = []

    if not paper_mode:
        reasons.append("paper_mode_required")
    if not strategy_ready:
        reasons.append("strategy_not_ready")
    if heartbeat_age_seconds is None:
        reasons.append("heartbeat_missing")
    elif heartbeat_age_seconds > max_heartbeat_age_seconds:
        reasons.append("heartbeat_stale")
    if drawdown_pct < -abs(max_drawdown_pct):
        reasons.append("drawdown_limit")

    return RuntimeGuardDecision(
        allowed=not reasons,
        reasons=tuple(reasons),
    )
