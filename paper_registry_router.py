"""Route paper-market events through the Phase 18/20 candidate registry.

This is the integration seam for the Phase 5 dashboard. It resolves the
registry's active candidate first and then delegates to PaperExecutionLoop.
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
    # The dashboard may already have constructed the loop without explicitly
    # passing a registry. Bind the requested registry before execution so the
    # execution layer and the integration seam use exactly the same source.
    loop.registry = registry

    symbol = str(market["symbol"])
    gate = get_active_candidate(registry, symbol)
    if not gate.allowed:
        return loop.on_market(
            market,
            candidate=None,
            exit_signal=exit_signal,
        )

    # ``PaperExecutionLoop`` resolves the candidate again at the execution
    # boundary. The candidate argument remains only for compatibility and is
    # deliberately not trusted for authorization.
    return loop.on_market(
        market,
        candidate=dict(gate.active.candidate),
        exit_signal=exit_signal,
    )
