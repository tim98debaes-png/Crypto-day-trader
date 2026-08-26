"""Phase 32 dashboard serialization and presentation-safety tests."""

from phase32_dashboard import build_snapshot


def test_phase32_snapshot_serializes_stable_primitives_only():
    snapshot = build_snapshot(
        active_candidate={"id": "candidate-1", "status": "ACTIVE"},
        open_positions=0,
        equity=1000.25,
        drawdown_pct=-1.25,
        allow_new_entries=True,
        heartbeat_age_seconds=12,
    )
    data = snapshot.as_dict()
    assert set(data) == {
        "status",
        "active_candidate_id",
        "active_candidate_status",
        "open_positions",
        "equity",
        "drawdown_pct",
        "allow_new_entries",
        "heartbeat_age_seconds",
        "alerts",
    }
    assert isinstance(data["alerts"], tuple)
    assert all(isinstance(value, (str, int, float, bool, type(None), tuple)) for value in data.values())


def test_phase32_degraded_snapshot_has_no_false_entry_permission():
    snapshot = build_snapshot(
        active_candidate=None,
        open_positions=0,
        equity=1000,
        drawdown_pct=-21,
        allow_new_entries=False,
        heartbeat_age_seconds=301,
    )
    data = snapshot.as_dict()
    assert data["allow_new_entries"] is False
    assert data["active_candidate_status"] is None
    assert snapshot.status == "DEGRADED"
