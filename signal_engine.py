"""Deterministic strategy signal adapter for paper trading.

This module deliberately does not invent a new trading strategy. It consumes
an optimizer-selected candidate and indicator snapshot, applies explicit
entry thresholds, and emits a normalized paper-trading signal.
"""

from dataclasses import dataclass
from typing import Optional

from paper_router import candidate_is_approved


@dataclass(frozen=True)
class TradingSignal:
    action: str
    direction: Optional[str] = None
    stop_distance: Optional[float] = None
    rr: Optional[float] = None
    reason: str = ""


def generate_signal(candidate: Optional[dict], indicators: dict) -> TradingSignal:
    if not candidate_is_approved(candidate or {}):
        return TradingSignal("WAIT", reason="quality_gates_failed")

    long_score = float(indicators.get("long_score", 0) or 0)
    short_score = float(indicators.get("short_score", 0) or 0)
    threshold = float(candidate.get("signal_threshold", 1.0) or 1.0)
    stop_distance = float(indicators.get("stop_distance", 0) or 0)
    rr = float(candidate.get("rr", indicators.get("rr", 2.0)) or 2.0)

    if stop_distance <= 0 or rr <= 0:
        return TradingSignal("WAIT", reason="invalid_risk_parameters")
    if long_score >= threshold and long_score > short_score:
        return TradingSignal("LONG", "LONG", stop_distance, rr, "long_threshold")
    if short_score >= threshold and short_score > long_score:
        return TradingSignal("SHORT", "SHORT", stop_distance, rr, "short_threshold")
    return TradingSignal("WAIT", reason="no_confirmed_signal")
