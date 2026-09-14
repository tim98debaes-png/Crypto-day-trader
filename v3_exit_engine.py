"""Deterministic state-aware exit policy for Strategy V3."""
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
    trail_atr_multiple: float


def adaptive_exit_policy(direction: str, entry_price: float, current_price: float,
                         stop_price: float, bars_open: int, setup_score: float,
                         regime: str, config: V3Config = V3Config(),
                         risk_distance: float | None = None,
                         partial_taken: bool = False) -> ExitDecision:
    if min(entry_price, current_price, stop_price) <= 0:
        raise ValueError("prices must be positive")
    risk = abs(entry_price - stop_price) if risk_distance is None else float(risk_distance)
    if risk <= 0 or bars_open < 0:
        raise ValueError("risk distance must be positive and bars_open non-negative")
    if direction == "LONG":
        stopped = current_price <= stop_price
        r = (current_price - entry_price) / risk
    elif direction == "SHORT":
        stopped = current_price >= stop_price
        r = (entry_price - current_price) / risk
    else:
        raise ValueError("direction must be LONG or SHORT")
    if stopped:
        return ExitDecision("CLOSE", "STOP", r, 0.0, 0.0, 0, 0.0)

    threshold = config.partial_at_r
    time_factor, runner = 1.0, 2.0
    trail = 1.8
    if regime in ("TREND_UP", "TREND_DOWN"):
        threshold *= 1.15; time_factor = 1.35; runner = 3.0; trail = 2.2
    elif regime == "RANGE":
        threshold *= 0.85; time_factor = 0.75; runner = 1.75; trail = 1.25
    elif regime == "HIGH_VOL":
        threshold *= 0.80; time_factor = 0.65; runner = 2.25; trail = 2.0
    elif regime in ("LOW_VOL", "TRANSITION"):
        threshold *= 0.90; time_factor = 0.80; runner = 2.0; trail = 1.6
    if setup_score >= config.strong_setup_score:
        threshold *= 1.08; time_factor *= 1.12; runner += 0.5; trail += 0.2

    threshold = max(0.75, min(1.75, threshold))
    runner = max(threshold + 0.25, min(4.0, runner))
    time_stop = max(1, round(config.time_stop_minutes / 5 * time_factor))

    if not partial_taken:
        if r >= threshold:
            return ExitDecision("PARTIAL", "ADAPTIVE_PARTIAL", r, threshold, runner, time_stop, trail)
        stale = max(12, round(time_stop * 0.55))
        if bars_open >= stale and r < -0.15:
            return ExitDecision("CLOSE", "ADAPTIVE_TIME_STOP", r, threshold, runner, time_stop, trail)
        if bars_open >= time_stop and r < 0.75:
            return ExitDecision("CLOSE", "ADAPTIVE_TIME_STOP", r, threshold, runner, time_stop, trail)
        return ExitDecision("HOLD", "HOLD", r, threshold, runner, time_stop, trail)

    if r >= runner:
        return ExitDecision("CLOSE", "ADAPTIVE_TARGET", r, threshold, runner, time_stop, trail)
    if r <= 0.0 and bars_open >= 4:
        return ExitDecision("CLOSE", "ADAPTIVE_CLOSE", r, threshold, runner, time_stop, trail)
    if bars_open >= time_stop and r < 0.75:
        return ExitDecision("CLOSE", "ADAPTIVE_TIME_STOP", r, threshold, runner, time_stop, trail)
    return ExitDecision("HOLD", "HOLD", r, threshold, runner, time_stop, trail)
