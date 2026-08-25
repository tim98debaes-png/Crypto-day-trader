"""Registry-backed dashboard view model.

The UI can use this read-only model for its active-candidate preview. It never
promotes, rolls back, or executes trades.
"""
from __future__ import annotations
from candidate_registry import CandidateRegistry
from active_candidate_source import get_active_candidate


def build_candidate_dashboard(registry: CandidateRegistry, symbol: str | None = None) -> dict:
    gate = get_active_candidate(registry, symbol)
    active = gate.active
    return {
        "allowed": gate.allowed,
        "reason": gate.reason,
        "active_candidate_id": active.candidate_id if active else None,
        "candidate": dict(active.candidate) if active else None,
        "status": "ACTIVE" if active else "NO_ACTIVE_CANDIDATE",
        "source": "candidate_registry",
    }


def build_candidate_rows(registry: CandidateRegistry) -> list[dict]:
    rows = []
    for entry in registry.list_candidates():
        candidate = dict(entry.get("candidate") or {})
        rows.append({
            "id": entry.get("id"),
            "status": entry.get("status"),
            "label": candidate.get("label", ""),
            "coin": candidate.get("Coin", candidate.get("symbol", "")),
            "oos_return_pct": candidate.get("OOS %"),
            "oos_profit_factor": candidate.get("OOS PF"),
            "oos_trades": candidate.get("OOS trades"),
            "oos_drawdown_pct": candidate.get("OOS DD"),
        })
    return rows
