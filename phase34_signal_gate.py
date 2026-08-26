"""Phase 34 pre-entry signal gate.

The gate is deliberately side-effect free: it evaluates runtime safety before
an execution loop may hand a signal to the paper engine.
"""
from __future__ import annotations

from dataclasses import dataclass

from phase34_runtime_guard import RuntimeGuardDecision, evaluate_entry_guard


@dataclass(frozen=True)
class SignalGateDecision:
    allowed: bool
    reason: str
    runtime: RuntimeGuardDecision


def evaluate_signal_entry(
    *,
    paper_mode: bool,
    strategy_ready: bool,
    heartbeat_age_seconds: float | None,
    drawdown_pct: float = 0.0,
    max_heartbeat_age_seconds: float = 300.0,
    max_drawdown_pct: float = 20.0,
) -> SignalGateDecision:
    runtime = evaluate_entry_guard(
        paper_mode=paper_mode,
        strategy_ready=strategy_ready,
        heartbeat_age_seconds=heartbeat_age_seconds,
        drawdown_pct=drawdown_pct,
        max_heartbeat_age_seconds=max_heartbeat_age_seconds,
        max_drawdown_pct=max_drawdown_pct,
    )
    if runtime.allowed:
        return SignalGateDecision(True, "allowed", runtime)
    return SignalGateDecision(False, runtime.reasons[0], runtime)
