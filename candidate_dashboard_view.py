"""Registry-backed dashboard view model."""
from __future__ import annotations

from datetime import datetime, timezone

from candidate_registry import CandidateRegistry
from active_candidate_source import get_active_candidate
from paper_session_observability import PaperSessionObserver


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


def build_session_dashboard(observer: PaperSessionObserver | None = None, limit: int = 20,
                            now: str | None = None) -> dict:
    """Expose Phase 22 health using an explicit clock when supplied by callers."""
    observer = observer or PaperSessionObserver()
    limit = max(1, int(limit))
    health_now = now
    if health_now is None and observer.checkpoints:
        # Dashboard reads are snapshots: when the caller does not provide a
        # reference clock, evaluate against the newest checkpoint so a freshly
        # rendered historical/test snapshot is not made stale by wall-clock time.
        health_now = observer.checkpoints[-1].timestamp
    return {
        "health": observer.health(now=health_now),
        "checkpoints": observer.export()[-limit:][::-1],
        "source": "paper_session_observability",
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
