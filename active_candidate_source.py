"""Controlled source of the active optimizer candidate for paper trading.

The registry is the source of truth. This module is read-only: it never
promotes, rolls back, or places orders. A paper-trading caller must request an
active candidate through this gate before generating an executable paper
signal.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from candidate_registry import CandidateRegistry
from paper_router import candidate_is_approved


@dataclass(frozen=True)
class ActiveCandidate:
    """Validated active candidate plus the registry version that selected it."""

    candidate_id: str
    candidate: dict[str, Any]


@dataclass(frozen=True)
class CandidateGate:
    """Result of asking whether a symbol may use the active candidate."""

    allowed: bool
    reason: str
    active: ActiveCandidate | None = None


def get_active_candidate(
    registry: CandidateRegistry,
    symbol: str | None = None,
) -> CandidateGate:
    """Return the active candidate only when the production safety gate passes.

    Research/paper experiments may use the softer gate in ``paper_router``
    explicitly. The registry's active candidate is a release-grade selection,
    so this read-only source deliberately validates it with production gates.
    """
    entry = registry.active()
    if entry is None:
        return CandidateGate(False, "no_active_candidate")

    candidate_id = str(entry.get("id", "")).strip()
    candidate = dict(entry.get("candidate") or {})
    if not candidate_id or not candidate:
        return CandidateGate(False, "invalid_active_candidate")

    if str(entry.get("status", "")).upper() != "ACTIVE":
        return CandidateGate(False, "active_registry_status_invalid")

    if symbol:
        requested = str(symbol).upper()
        candidate_symbol = candidate.get("Coin", candidate.get("symbol"))
        if candidate_symbol and str(candidate_symbol).upper() != requested:
            return CandidateGate(False, "candidate_symbol_mismatch")

    if not candidate_is_approved(candidate, mode="production"):
        return CandidateGate(False, "quality_gates_failed")

    return CandidateGate(
        True,
        "active_candidate_approved",
        ActiveCandidate(candidate_id, candidate),
    )
