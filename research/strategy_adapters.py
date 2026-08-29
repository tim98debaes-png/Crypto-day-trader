"""Explicit strategy adapter contract for Step 2b.

Adapters are intentionally small: each receives only information available at
or before the current candle and returns a normalized signal mapping. This
prevents the benchmark from silently mixing execution logic with strategy logic.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping

Signal = Mapping[str, object]
StrategyAdapter = Callable[[list[float]], Signal | None]


def legacy_adapter(prices: list[float]) -> Signal | None:
    """Placeholder for the exact legacy extraction from the v8.5 research app."""
    raise NotImplementedError("Legacy adapter must be extracted from app.py before A/B/C execution")


def current_adapter(prices: list[float]) -> Signal | None:
    from entry_exit_logic_v2 import entry_signal_details
    for direction in ("LONG", "SHORT"):
        ready, reason, score, diagnostics = entry_signal_details(prices, direction)
        if ready:
            return {"action": direction, "reason": reason, "score": score, "diagnostics": diagnostics}
    return {"action": "WAIT", "reason": "no_confirmed_signal"}


def hybrid_adapter(prices: list[float]) -> Signal | None:
    """Reserved for a pre-registered hybrid; never silently invent parameters."""
    raise NotImplementedError("Hybrid adapter must be explicitly defined after A/B baseline results")
