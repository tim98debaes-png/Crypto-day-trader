"""Phase 33 release-hardening smoke contracts."""

from dataclasses import FrozenInstanceError

import pytest

from phase32_dashboard import build_snapshot


def test_phase32_snapshot_is_immutable_and_has_stable_contract():
    snapshot = build_snapshot(
        active_candidate={"id": "candidate-33", "status": "ACTIVE"},
        open_positions=2,
        equity=1500.0,
        drawdown_pct=-2.5,
        allow_new_entries=True,
        heartbeat_age_seconds=15,
    )

    assert snapshot.status == "HEALTHY"
    assert snapshot.active_candidate_id == "candidate-33"
    assert snapshot.open_positions == 2
    assert snapshot.allow_new_entries is True
    assert isinstance(snapshot.alerts, tuple)

    with pytest.raises(FrozenInstanceError):
        snapshot.status = "DEGRADED"


def test_phase32_degraded_snapshot_blocks_entries_and_exposes_alerts():
    snapshot = build_snapshot(
        active_candidate=None,
        open_positions=0,
        equity=700.0,
        drawdown_pct=-25.0,
        allow_new_entries=False,
        heartbeat_age_seconds=301,
    )

    assert snapshot.status == "DEGRADED"
    assert snapshot.allow_new_entries is False
    assert snapshot.alerts == (
        "no_active_candidate",
        "stale_heartbeat",
        "drawdown_limit",
        "new_entries_blocked",
    )
