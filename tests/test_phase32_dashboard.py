"""Phase 32 dashboard model tests."""

from phase32_dashboard import build_snapshot


def test_phase32_healthy_snapshot():
    snapshot = build_snapshot(
        active_candidate={"id": "abc123", "status": "ACTIVE"},
        open_positions=1,
        equity=1050,
        drawdown_pct=-4,
        allow_new_entries=True,
        heartbeat_age_seconds=30,
    )
    assert snapshot.status == "HEALTHY"
    assert snapshot.alerts == ()
    assert snapshot.as_dict()["active_candidate_id"] == "abc123"


def test_phase32_degraded_snapshot_reports_all_alerts():
    snapshot = build_snapshot(
        active_candidate=None,
        open_positions=0,
        equity=800,
        drawdown_pct=-25,
        allow_new_entries=False,
        heartbeat_age_seconds=600,
    )
    assert snapshot.status == "DEGRADED"
    assert snapshot.alerts == (
        "no_active_candidate",
        "stale_heartbeat",
        "drawdown_limit",
        "new_entries_blocked",
    )


def test_phase32_boundary_values_are_healthy():
    snapshot = build_snapshot(
        active_candidate={"id": "abc", "status": "ACTIVE"},
        open_positions=0,
        equity=1000,
        drawdown_pct=-20,
        allow_new_entries=True,
        heartbeat_age_seconds=300,
    )
    assert snapshot.status == "HEALTHY"
