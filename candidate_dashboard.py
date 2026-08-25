"""Dashboard-facing adapter for the Phase 18 candidate registry.

This module keeps Streamlit concerns out of the registry itself. It exposes a
small, read/write-safe interface for showing the active candidate and requesting
an explicit rollback. It never places orders.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from candidate_registry import CandidateRegistry


def registry_snapshot(registry: CandidateRegistry) -> dict[str, Any]:
    """Return a UI-safe snapshot of active candidate and recent audit events."""
    active = registry.active()
    history = registry.history()
    return {
        "active": dict(active) if active else None,
        "active_id": active.get("id") if active else None,
        "active_status": active.get("status") if active else "NONE",
        "history": history[-20:],
    }


def request_rollback(
    registry: CandidateRegistry,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    """Perform an explicit registry rollback and return its audit result."""
    restored = registry.rollback(candidate_id)
    snapshot = registry_snapshot(registry)
    return {
        "restored_id": restored,
        "active_id": snapshot["active_id"],
        "status": snapshot["active_status"],
        "event": snapshot["history"][-1] if snapshot["history"] else None,
    }


def candidate_table(registry: CandidateRegistry) -> list[dict[str, Any]]:
    """Return registered candidates in deterministic ID order for a table."""
    data = registry._load()
    rows = []
    for candidate_id, entry in sorted(data["candidates"].items()):
        candidate = dict(entry.get("candidate") or {})
        rows.append(
            {
                "id": candidate_id,
                "status": entry.get("status"),
                "created_at": entry.get("created_at"),
                "promoted_at": entry.get("promoted_at"),
                "label": candidate.get("label", candidate.get("Strategy", "-")),
                "OOS %": candidate.get("OOS %"),
                "OOS PF": candidate.get("OOS PF"),
                "OOS trades": candidate.get("OOS trades"),
                "OOS DD": candidate.get("OOS DD"),
            }
        )
    return rows
