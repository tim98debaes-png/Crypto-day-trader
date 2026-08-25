import pytest

from paper_engine import PaperAccount
from paper_session_observability import (
    DEGRADED,
    HEALTHY,
    INVALID,
    STALE,
    PaperSessionObserver,
    build_checkpoint,
)


def summary(**overrides):
    value = {
        "equity": 1000.0,
        "closed_trades": 0,
        "profit_factor": 0.0,
        "return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "open_positions": 0,
        "monitor_status": "HEALTHY",
    }
    value.update(overrides)
    return value


def test_heartbeat_creates_integrity_checked_checkpoint():
    observer = PaperSessionObserver(stale_after_seconds=900)
    checkpoint = observer.heartbeat(summary(), active_candidate_id="abc", timestamp="2026-08-25T19:00:00+00:00")

    assert checkpoint.sequence == 1
    assert checkpoint.active_candidate_id == "abc"
    assert observer.health("2026-08-25T19:05:00+00:00")["status"] == HEALTHY


def test_profit_factor_infinity_is_safe_for_observability():
    observer = PaperSessionObserver()
    checkpoint = observer.heartbeat(summary(profit_factor=float("inf")), active_candidate_id="abc")

    assert checkpoint.profit_factor == 1_000_000.0


def test_sequence_gap_is_rejected():
    observer = PaperSessionObserver()
    observer.heartbeat(summary(), active_candidate_id="abc", timestamp="2026-08-25T19:00:00+00:00")
    second = build_checkpoint(summary(), sequence=3, active_candidate_id="abc", timestamp="2026-08-25T19:01:00+00:00")

    with pytest.raises(ValueError, match="sequence gap"):
        observer.record(second)


def test_tampered_checkpoint_hash_is_rejected():
    observer = PaperSessionObserver()
    checkpoint = observer.heartbeat(summary(), active_candidate_id="abc", timestamp="2026-08-25T19:00:00+00:00")
    tampered = type(checkpoint)(
        **{**checkpoint.__dict__, "equity": 900.0}
    )

    with pytest.raises(ValueError, match="integrity hash"):
        observer.record(tampered)


def test_stale_heartbeat_is_detected():
    observer = PaperSessionObserver(stale_after_seconds=60)
    observer.heartbeat(summary(), active_candidate_id="abc", timestamp="2026-08-25T19:00:00+00:00")

    health = observer.health("2026-08-25T19:02:01+00:00")

    assert health["status"] == STALE
    assert health["reason"] == "heartbeat_stale"


def test_monitor_block_is_degraded_but_not_hidden():
    observer = PaperSessionObserver(stale_after_seconds=900)
    observer.heartbeat(summary(monitor_status="BLOCKED"), active_candidate_id=None, timestamp="2026-08-25T19:00:00+00:00")

    health = observer.health("2026-08-25T19:01:00+00:00")

    assert health["status"] == DEGRADED
    assert health["reason"] == "paper_monitor_blocked"


def test_no_checkpoint_is_invalid():
    assert PaperSessionObserver().health("2026-08-25T19:00:00+00:00")["status"] == INVALID


def test_paper_execution_loop_emits_heartbeats(tmp_path):
    from candidate_registry import CandidateRegistry
    from paper_execution import PaperExecutionLoop

    candidate = {
        "Status": "ROBUST",
        "Coin": "BTCUSDT",
        "OOS %": 4.0,
        "OOS PF": 1.5,
        "OOS trades": 20,
        "OOS DD": -8.0,
        "Stability": 75,
        "MC P05 %": 2.0,
        "Direction": "LONG",
        "RR": 2.0,
    }
    registry = CandidateRegistry(tmp_path / "registry.json")
    candidate_id = registry.register(candidate)
    registry.promote(candidate_id, human_approved=True)
    account = PaperAccount(capital=1000.0, cash=1000.0)
    observer = PaperSessionObserver()
    loop = PaperExecutionLoop(account, registry=registry, observer=observer)

    result = loop.on_market({
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "price": 100.0,
        "stop_distance": 2.0,
        "rr": 2.0,
        "timestamp": "2026-08-25T19:00:00+00:00",
    })

    assert result["action"] == "OPEN"
    assert len(observer.checkpoints) == 1
    assert observer.checkpoints[-1].active_candidate_id == candidate_id
