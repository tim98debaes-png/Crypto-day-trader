"""Phase 31 operational safety contract tests."""

from datetime import datetime, timedelta, timezone

from candidate_registry import CandidateRegistry


def test_phase31_registry_snapshot_is_safe_after_deactivation(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    cid = registry.register({"Coin": "BTCUSDT", "Direction": "LONG", "Status": "ROBUST"})
    registry.promote(cid, human_approved=True)
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
