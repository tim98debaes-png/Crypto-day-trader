"""Deterministic adaptive exit policy for Strategy V3.

The policy uses only information available while a trade is open. It is a
state machine: before a partial it seeks to monetize a proven move; after a
partial it protects the remaining runner and can close stale/failing trades.
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
    risk_distance: float | None = None,
    partial_taken: bool = False,
) -> ExitDecision:
    """Return HOLD, PARTIAL or CLOSE using current trade state only.

    R is always anchored to the original stop distance when supplied.  The
    policy never uses future MAE/MFE information. ``partial_taken`` prevents
    repeated partial instructions and changes the runner-management rules.
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
        return ExitDecision("CLOSE", "STOP", r, 0.0, 0)

    # Base profit-taking level.  Trend trades keep a larger runner; unstable
    # regimes monetize sooner because continuation is less reliable.
    threshold = config.partial_at_r
    time_factor = 1.0
    if regime in ("TREND_UP", "TREND_DOWN"):
        threshold *= 1.15
        time_factor = 1.30
    elif regime == "RANGE":
        threshold *= 0.85
        time_factor = 0.75
    elif regime == "HIGH_VOL":
        threshold *= 0.80
        time_factor = 0.65
    elif regime in ("LOW_VOL", "TRANSITION"):
        threshold *= 0.90
        time_factor = 0.75

    if setup_score >= config.strong_setup_score:
        threshold *= 1.10
        time_factor *= 1.10

    threshold = max(0.75, min(1.75, threshold))
    time_stop_bars = max(1, round(config.time_stop_minutes / 5 * time_factor))

    if not partial_taken:
        if r >= threshold:
            return ExitDecision("PARTIAL", "ADAPTIVE_PARTIAL", r, threshold, time_stop_bars)
        # A trade that fails to develop should not be allowed to consume the
        # entire nominal time stop while sitting near/below entry.
        stale_bars = max(12, round(time_stop_bars * 0.55))
        if bars_open >= stale_bars and r < 0.0:
            return ExitDecision("CLOSE", "ADAPTIVE_TIME_STOP", r, threshold, time_stop_bars)
        return ExitDecision("HOLD", "HOLD", r, threshold, time_stop_bars)

    # After banking half, protect the runner.  A meaningful retracement back
    # below +0.25R is no longer attractive after the trade already proved
    # itself; the breakeven stop in PaperAccount is the final safety net.
    if r <= 0.20 and bars_open >= 6:
        return ExitDecision("CLOSE", "ADAPTIVE_CLOSE", r, threshold, time_stop_bars)
    if bars_open >= time_stop_bars and r < 0.75:
        return ExitDecision("CLOSE", "ADAPTIVE_TIME_STOP", r, threshold, time_stop_bars)
    return ExitDecision("HOLD", "HOLD", r, threshold, time_stop_bars)
