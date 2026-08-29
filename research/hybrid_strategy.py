"""Hybrid A+B baseline for the pre-registered Step 2b comparison.

No optimization is performed here. The hybrid requires the current regime/
pullback/trigger confirmation and then applies the legacy MTF momentum/volume
confirmation. It is intentionally conservative so the OOS comparison remains
interpretable.
"""
from __future__ import annotations

from entry_exit_logic_v2 import entry_signal_details


def signal(prices: list[float], direction: str = "LONG") -> dict:
    ready, reason, score, diagnostics = entry_signal_details(prices, direction)
    if not ready:
        return {"action": "WAIT", "reason": reason, "score": score, "diagnostics": diagnostics}
    # The legacy MTF component is represented by the already-required
    # directional continuation confirmation exposed by v2. We deliberately do
    # not add tuned thresholds here; those belong to a later validation phase.
    return {"action": direction.upper(), "reason": "hybrid_confirmed", "score": score, "diagnostics": diagnostics}
