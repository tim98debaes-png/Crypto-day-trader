"""Phase 32 integration contract tests for the application dashboard model."""

from phase32_dashboard import build_snapshot


def test_phase32_dashboard_exposes_safe_entry_state():
    snapshot = build_snapshot(
        active_candidate={"id": "candidate-1", "status": "ACTIVE"},
        open_positions=2,
        equity=1025.0,
        drawdown_pct=-2.5,
        allow_new_entries=True,
        heartbeat_age_seconds=15,
    )
    data = snapshot.as_dict()
    assert data["status"] == "HEALTHY"
    assert data["allow_new_entries"] is True
    assert data["open_positions"] == 2
    assert data["active_candidate_id"] == "candidate-1"


def test_phase32_dashboard_blocks_entries_when_degraded():
    snapshot = build_snapshot(
        active_candidate=None,
        open_positions=1,
        equity=750.0,
        drawdown_pct=-30.0,
        allow_new_entries=False,
        heartbeat_age_seconds=900,
    )
    data = snapshot.as_dict()
    assert data["status"] == "DEGRADED"
    assert data["allow_new_entries"] is False
    assert "stale_heartbeat" in data["alerts"]
    assert "drawdown_limit" in data["alerts"]
