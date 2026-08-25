from candidate_dashboard import candidate_table, registry_snapshot, request_rollback
from candidate_registry import CandidateRegistry


def candidate(label="A"):
    return {
        "Status": "ROBUST",
        "label": label,
        "OOS %": 4.0,
        "OOS PF": 1.5,
        "OOS trades": 20,
        "OOS DD": -8.0,
        "Stability": 75,
        "MC P05 %": 2.0,
    }


def test_snapshot_and_table_are_ui_safe(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    cid = registry.register(candidate())

    snapshot = registry_snapshot(registry)
    rows = candidate_table(registry)

    assert snapshot["active"] is None
    assert snapshot["active_id"] is None
    assert rows[0]["id"] == cid
    assert rows[0]["status"] == "REGISTERED"
    assert rows[0]["OOS PF"] == 1.5


def test_dashboard_rollback_returns_audited_result(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    first = registry.register(candidate("A"))
    second = registry.register(candidate("B"))
    registry.promote(first, human_approved=True)
    registry.promote(second, human_approved=True)

    result = request_rollback(registry, first)

    assert result["restored_id"] == first
    assert result["active_id"] == first
    assert result["status"] == "ACTIVE"
    assert result["event"]["event"] == "ROLLBACK"
