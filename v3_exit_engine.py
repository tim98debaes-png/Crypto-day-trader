"""Deterministic adaptive exit policy for Strategy V3.

The policy uses only information available while a trade is open. MAE/MFE
statistics are deliberately not used to set thresholds here; they are used
for later research and validation so the live decision path stays free of
hindsight leakage.
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
) -> ExitDecision:
    """Return HOLD, PARTIAL or CLOSE using current trade state only."""
    if entry_price <= 0 or stop_price <= 0 or current_price <= 0:
        raise ValueError("prices must be positive")
    risk = abs(entry_price - stop_price)
    if risk <= 0:
        raise ValueError("stop must differ from entry")

    if direction == "LONG":
        stopped = current_price <= stop_price
        r = (current_price - entry_price) / risk
    elif direction == "SHORT":
        stopped = current_price >= stop_price
        r = (entry_price - current_price) / risk
    else:
        raise ValueError("direction must be LONG or SHORT")

    if stopped:
        return ExitDecision("CLOSE", "STOP", r, 0.0, 0)

    # Trend trades get more room; unstable/ranging regimes monetize earlier.
    threshold = config.partial_at_r
    time_factor = 1.0
    if regime in ("TREND_UP", "TREND_DOWN"):
        threshold *= 1.25
        time_factor = 1.35
    elif regime == "RANGE":
        threshold *= 0.90
        time_factor = 0.80
    elif regime == "HIGH_VOL":
        threshold *= 0.80
        time_factor = 0.70
    elif regime in ("LOW_VOL", "TRANSITION"):
        threshold *= 0.90
        time_factor = 0.75

    if setup_score >= config.strong_setup_score:
        threshold *= 1.20
        time_factor *= 1.15

    threshold = max(0.50, min(2.00, threshold))
    time_stop_bars = max(1, round(config.time_stop_minutes / 5 * time_factor))

    if r >= threshold:
        return ExitDecision("PARTIAL", "ADAPTIVE_PARTIAL", r, threshold, time_stop_bars)
    if bars_open >= time_stop_bars and r < 0.25:
        return ExitDecision("CLOSE", "ADAPTIVE_TIME_STOP", r, threshold, time_stop_bars)
    return ExitDecision("HOLD", "HOLD", r, threshold, time_stop_bars)
