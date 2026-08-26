"""Read-only adapter from existing application state to Phase 32 dashboard."""
from __future__ import annotations

from typing import Any, Mapping

from phase32_dashboard import DashboardSnapshot, build_snapshot


def build_app_dashboard_snapshot(
    *,
    active_candidate: Mapping[str, Any] | None,
    portfolio: Any,
    allow_new_entries: bool,
    heartbeat_age_seconds: float,
) -> DashboardSnapshot:
    """Build a dashboard snapshot without mutating application state."""
    positions = getattr(portfolio, "positions", None)
    if positions is None and isinstance(portfolio, Mapping):
        positions = portfolio.get("positions", {})
    if positions is None:
        positions = {}

    equity = getattr(portfolio, "equity", None)
    if equity is None and isinstance(portfolio, Mapping):
        equity = portfolio.get("equity")
    if equity is None:
        equity = getattr(portfolio, "cash", 0.0)

    drawdown_pct = getattr(portfolio, "drawdown_pct", None)
    if drawdown_pct is None and isinstance(portfolio, Mapping):
        drawdown_pct = portfolio.get("drawdown_pct", 0.0)
    if drawdown_pct is None:
        drawdown_pct = 0.0

    return build_snapshot(
        active_candidate=active_candidate,
        open_positions=len(positions),
        equity=float(equity),
        drawdown_pct=float(drawdown_pct),
        allow_new_entries=bool(allow_new_entries),
        heartbeat_age_seconds=float(heartbeat_age_seconds),
    )
