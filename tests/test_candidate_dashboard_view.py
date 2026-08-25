from candidate_dashboard_view import build_candidate_dashboard, build_candidate_rows
from candidate_registry import CandidateRegistry


def candidate(coin="BTCUSDT"):
    return {"Status":"ROBUST","Coin":coin,"OOS %":4.0,"OOS PF":1.5,"OOS trades":20,"OOS DD":-8.0,"Stability":75,"MC P05 %":2.0}


def test_dashboard_is_fail_closed_without_active_candidate(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    view = build_candidate_dashboard(registry, "BTCUSDT")
    assert view["allowed"] is False
    assert view["status"] == "NO_ACTIVE_CANDIDATE"
    assert view["active_candidate_id"] is None
    assert view["source"] == "candidate_registry"


def test_dashboard_uses_registry_active_candidate(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    cid = registry.register(candidate())
    assert registry.promote(cid, human_approved=True).approved
    view = build_candidate_dashboard(registry, "BTCUSDT")
    assert view["allowed"] is True
    assert view["status"] == "ACTIVE"
    assert view["active_candidate_id"] == cid
    assert view["candidate"]["Coin"] == "BTCUSDT"


def test_dashboard_rows_are_registry_candidates(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    cid = registry.register(candidate())
    rows = build_candidate_rows(registry)
    assert len(rows) == 1
    assert rows[0]["id"] == cid
    assert rows[0]["coin"] == "BTCUSDT"
    assert rows[0]["oos_profit_factor"] == 1.5
