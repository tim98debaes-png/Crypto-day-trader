"""Route paper-market events through the Phase 18/20 candidate registry.

This is the integration seam for the Phase 5 dashboard. It resolves the
registry's active candidate first and only then delegates to PaperExecutionLoop.
No registry mutation and no live exchange calls occur here.
"""
from __future__ import annotations

from candidate_registry import CandidateRegistry
from active_candidate_source import get_active_candidate
from paper_execution import PaperExecutionLoop


def on_registry_market(
    loop: PaperExecutionLoop,
    registry: CandidateRegistry,
    market: dict,
    *,
    exit_signal: bool = False,
) -> dict:
    """Process one paper market event using only the active registry candidate."""
    symbol = str(market["symbol"])
    gate = get_active_candidate(registry, symbol)
    if not gate.allowed:
        # Still let the execution loop manage an already-open position, but
        # never allow a new position to use a stale/session-only candidate.
        if loop.account.position is not None:
            return loop.on_market(
                market,
                candidate=None,
                exit_signal=exit_signal,
            )
        return loop.on_market(
            market,
            candidate=None,
            exit_signal=exit_signal,
        )

    candidate = dict(gate.active.candidate)
    candidate["registry_candidate_id"] = gate.active.candidate_id
    return loop.on_market(
        market,
        candidate=candidate,
        exit_signal=exit_signal,
    )
