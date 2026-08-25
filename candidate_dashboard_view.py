"""Registry-backed dashboard view model.

The UI can use this read-only model for the active-candidate preview and the
Phase 21 monitoring audit. It never promotes, rolls back, or executes trades.
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


def build_monitor_dashboard(registry: CandidateRegistry, limit: int = 20) -> dict:
    """Expose the latest Phase 21 monitor state and audit trail read-only."""
    limit = max(1, int(limit))
    events = [event for event in registry.history() if event.get("event") == "MONITOR_DECISION"]
    latest = events[-1] if events else None
    return {
        "status": latest.get("status") if latest else "NO_DATA",
        "reason": latest.get("reason") if latest else "no_monitor_data",
        "active_id": latest.get("active_id") if latest else None,
        "target_id": latest.get("target_id") if latest else None,
        "allow_new_entries": bool(latest.get("allow_new_entries")) if latest else False,
        "breaches": list(latest.get("breaches", [])) if latest else [],
        "metrics": dict(latest.get("metrics", {})) if latest else {},
        "events": list(reversed(events[-limit:])),
        "source": "candidate_registry.monitor_events",
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
