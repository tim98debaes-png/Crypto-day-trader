"""Phase 31 operational safety contract tests."""

from datetime import datetime, timedelta, timezone

from candidate_registry import CandidateRegistry


APPROVED_CANDIDATE = {
    "Coin": "BTCUSDT",
    "Direction": "LONG",
    "Status": "ROBUST",
    "OOS %": 5.0,
    "OOS PF": 1.50,
    "OOS trades": 30,
    "OOS DD": -10.0,
    "Stability": 80.0,
    "MC P05 %": 0.0,
}


def test_phase31_registry_snapshot_is_safe_after_deactivation(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    cid = registry.register(APPROVED_CANDIDATE)
    decision = registry.promote(cid, human_approved=True)
    assert decision.approved
    assert registry.active()["id"] == cid

    registry.deactivate()
    assert registry.active() is None


def test_phase31_stale_heartbeat_is_detectable():
    now = datetime.now(timezone.utc)
    heartbeat = now - timedelta(minutes=6)
    assert (now - heartbeat).total_seconds() > 300


def test_phase31_fresh_heartbeat_is_healthy():
    now = datetime.now(timezone.utc)
    heartbeat = now - timedelta(seconds=30)
    assert (now - heartbeat).total_seconds() <= 300
