"""Phase 32: small, UI-agnostic operational dashboard model.

The Streamlit layer can render this model without duplicating trading logic.
This module is read-only: it never changes positions or places orders.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class DashboardSnapshot:
    status: str
    active_candidate_id: str | None
    active_candidate_status: str | None
    open_positions: int
    equity: float
    drawdown_pct: float
    allow_new_entries: bool
    heartbeat_age_seconds: float | None
    alerts: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_snapshot(
    *,
    active_candidate: dict[str, Any] | None,
    open_positions: int,
    equity: float,
    drawdown_pct: float,
    allow_new_entries: bool,
    heartbeat_age_seconds: float | None,
    max_heartbeat_age_seconds: float = 300.0,
) -> DashboardSnapshot:
    """Build a deterministic, read-only operational snapshot."""
    alerts: list[str] = []
    if active_candidate is None:
        alerts.append("no_active_candidate")
    if heartbeat_age_seconds is not None and heartbeat_age_seconds > max_heartbeat_age_seconds:
        alerts.append("stale_heartbeat")
    if drawdown_pct < -20.0:
        alerts.append("drawdown_limit")
    if not allow_new_entries:
        alerts.append("new_entries_blocked")

    status = "HEALTHY" if not alerts else "DEGRADED"
    return DashboardSnapshot(
        status=status,
        active_candidate_id=active_candidate.get("id") if active_candidate else None,
        active_candidate_status=active_candidate.get("status") if active_candidate else None,
        open_positions=int(open_positions),
        equity=float(equity),
        drawdown_pct=float(drawdown_pct),
        allow_new_entries=bool(allow_new_entries),
        heartbeat_age_seconds=(float(heartbeat_age_seconds) if heartbeat_age_seconds is not None else None),
        alerts=tuple(alerts),
    )
