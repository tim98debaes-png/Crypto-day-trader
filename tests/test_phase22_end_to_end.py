from candidate_registry import CandidateRegistry
from paper_engine import PaperAccount
from paper_execution import PaperExecutionLoop
from paper_session_observability import PaperSessionObserver


def candidate(label, direction="LONG"):
    return {
        "Status": "ROBUST",
        "label": label,
        "Coin": "BTCUSDT",
        "Direction": direction,
        "RR": 2.0,
        "OOS %": 4.0,
        "OOS PF": 1.5,
        "OOS trades": 20,
        "OOS DD": -8.0,
        "Stability": 75,
        "MC P05 %": 2.0,
    }


def seed_losses(account, count=20):
    for index in range(count):
        account.audit_log.append({
            "event": "CLOSE",
            "pnl": -1.0,
            "timestamp": f"2026-08-25T00:{index:02d}:00+00:00",
        })


def test_end_to_end_candidate_registry_monitor_rollback_and_observer_recovery(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    fallback_id = registry.register(candidate("fallback"))
    registry.promote(fallback_id, human_approved=True)
    active_id = registry.register(candidate("active"))
    registry.promote(active_id, human_approved=True)

    account = PaperAccount(capital=1000.0)
    seed_losses(account, 20)
    observer_path = tmp_path / "observability.json"
    observer = PaperSessionObserver(state_path=str(observer_path))
    loop = PaperExecutionLoop(account, registry=registry, observer=observer)

    result = loop.on_market({
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "price": 100.0,
        "stop_distance": 2.0,
        "rr": 2.0,
        "timestamp": "2026-08-25T19:00:00+00:00",
    })

    assert result["action"] == "WAIT"
    assert result["monitor_status"] == "BLOCKED"
    assert registry.active()["id"] == fallback_id
    assert registry.get(active_id)["status"] == "ROLLED_BACK"
    assert observer.checkpoints[-1].active_candidate_id == fallback_id

    recovered_observer = PaperSessionObserver(state_path=str(observer_path))
    assert recovered_observer.checkpoints[-1].sequence == observer.checkpoints[-1].sequence
    assert recovered_observer.health("2026-08-25T19:01:00+00:00")["status"] == "DEGRADED"
