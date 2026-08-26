"""Phase 32 Streamlit rendering helpers.

Rendering only: this module consumes an already-built DashboardSnapshot and
never mutates trading state or places orders.
"""
from __future__ import annotations

from typing import Any

from phase32_dashboard import DashboardSnapshot


def dashboard_payload(snapshot: DashboardSnapshot) -> dict[str, Any]:
    """Return the stable payload used by the Streamlit presentation layer."""
    return snapshot.as_dict()


def render_dashboard(st_module: Any, snapshot: DashboardSnapshot) -> None:
    """Render an operational dashboard without embedding trading logic."""
    data = dashboard_payload(snapshot)
    st_module.subheader("Operational status")
    st_module.metric("Status", data["status"])
    st_module.metric("Equity", f"{data['equity']:.2f}")
    st_module.metric("Drawdown", f"{data['drawdown_pct']:.2f}%")
    st_module.metric("Open positions", data["open_positions"])
    st_module.metric("New entries", "ALLOWED" if data["allow_new_entries"] else "BLOCKED")
    st_module.caption(f"Active candidate: {data['active_candidate_id'] or 'none'}")
    if data["alerts"]:
        for alert in data["alerts"]:
            st_module.warning(alert)
