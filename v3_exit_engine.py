"""Deterministic adaptive exit policy for Strategy V3.

The policy is a state machine: before a partial it seeks to monetize a
proven move; after a partial it protects the remaining runner and can close
stale, retracing, or fully developed trades. Decisions use only information
available while the trade is open.
"""
from __future__ import annotations

from dataclasses import dataclass

from strategy_v3 import V3Config


@dataclass(frozen=True)
class ExitDecision:
    action: str
    reason: str
    r_multiple: float
    partial_threshold_r: float
    runner_target_r: float
    time_stop_bars: int


def adaptive_exit_policy(
    direction: str,
    entry_price: float,
    current_price: float,
    stop_price: float,
    bars_open: int,
    setup_score: float,
    regime: str,
    config: V3Config = V3Config(),
    risk_distance: float | None = None,
    partial_taken: bool = False,
) -> ExitDecision:
    """Return HOLD, PARTIAL or CLOSE from current trade state only.

    R is anchored to the original stop distance when supplied. The runner
    target is regime-aware but fixed before the outcome is known, avoiding
    MAE/MFE hindsight leakage.
    """
    if entry_price <= 0 or stop_price <= 0 or current_price <= 0:
        raise ValueError("prices must be positive")
    risk = abs(entry_price - stop_price) if risk_distance is None else float(risk_distance)
    if risk <= 0:
        raise ValueError("risk distance must be positive")
    if bars_open < 0:
        raise ValueError("bars_open must be non-negative")

    if direction == "LONG":
        stopped = current_price <= stop_price
        r = (current_price - entry_price) / risk
    elif direction == "SHORT":
        stopped = current_price >= stop_price
        r = (entry_price - current_price) / risk
    else:
        raise ValueError("direction must be LONG or SHORT")

    if stopped:
        return ExitDecision("CLOSE", "STOP", r, 0.0, 0.0, 0)

    threshold = config.partial_at_r
    time_factor = 1.0
    runner_target = 2.0
    if regime in ("TREND_UP", "TREND_DOWN"):
        threshold *= 1.15
        time_factor = 1.30
        runner_target = 3.0
    elif regime == "RANGE":
        threshold *= 0.85
        time_factor = 0.75
        runner_target = 1.75
    elif regime == "HIGH_VOL":
        threshold *= 0.80
        time_factor = 0.65
        runner_target = 2.25
    elif regime in ("LOW_VOL", "TRANSITION"):
        threshold *= 0.90
        time_factor = 0.75
        runner_target = 2.0

    if setup_score >= config.strong_setup_score:
        threshold *= 1.10
        time_factor *= 1.10
        runner_target += 0.50

    threshold = max(0.75, min(1.75, threshold))
    runner_target = max(threshold + 0.25, min(4.0, runner_target))
    time_stop_bars = max(1, round(config.time_stop_minutes / 5 * time_factor))

    if not partial_taken:
        if r >= threshold:
            return ExitDecision("PARTIAL", "ADAPTIVE_PARTIAL", r, threshold, runner_target, time_stop_bars)
        stale_bars = max(12, round(time_stop_bars * 0.55))
        if bars_open >= stale_bars and r < 0.0:
            return ExitDecision("CLOSE", "ADAPTIVE_TIME_STOP", r, threshold, runner_target, time_stop_bars)
        return ExitDecision("HOLD", "HOLD", r, threshold, runner_target, time_stop_bars)

    # Once half is banked, do not give back a fully developed move.
    if r >= runner_target:
        return ExitDecision("CLOSE", "ADAPTIVE_TARGET", r, threshold, runner_target, time_stop_bars)
    if r <= 0.20 and bars_open >= 6:
        return ExitDecision("CLOSE", "ADAPTIVE_CLOSE", r, threshold, runner_target, time_stop_bars)
    if bars_open >= time_stop_bars and r < 0.75:
        return ExitDecision("CLOSE", "ADAPTIVE_TIME_STOP", r, threshold, runner_target, time_stop_bars)
    return ExitDecision("HOLD", "HOLD", r, threshold, runner_target, time_stop_bars)
