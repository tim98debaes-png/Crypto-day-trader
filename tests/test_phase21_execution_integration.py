from candidate_registry import CandidateRegistry
from paper_engine import PaperAccount
from paper_execution import PaperExecutionLoop
from paper_session_monitor import snapshot_from_account


def approved_candidate(label="A"):
    return {
        "Status": "ROBUST",
        "label": label,
        "Coin": "BTCUSDT",
        "Direction": "LONG",
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


def test_execution_loop_blocks_new_entry_after_hard_monitor_breach(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    candidate_id = registry.register(approved_candidate())
    registry.promote(candidate_id, human_approved=True)

    account = PaperAccount(capital=1000.0)
    seed_losses(account, 20)
    loop = PaperExecutionLoop(account, registry)

    result = loop.on_market({
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "price": 100.0,
        "stop_distance": 2.0,
        "rr": 2.0,
        "timestamp": "2026-08-25T12:00:00+00:00",
    })

    assert result["action"] == "WAIT"
    assert result["reason"] == "paper_monitor_blocked"
    assert result["monitor_status"] == "BLOCKED"
    assert account.position is None
    assert registry.active() is None


def test_execution_loop_allows_entry_when_monitor_is_healthy(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    candidate_id = registry.register(approved_candidate())
    registry.promote(candidate_id, human_approved=True)

    account = PaperAccount(capital=1000.0)
    loop = PaperExecutionLoop(account, registry)

    result = loop.on_market({
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "price": 100.0,
        "stop_distance": 2.0,
        "rr": 2.0,
        "timestamp": "2026-08-25T12:00:00+00:00",
    })

    assert result["action"] == "OPEN"
    assert result["candidate_id"] == candidate_id
    assert result["monitor_status"] == "HEALTHY"
    assert account.position is not None


def test_existing_position_can_exit_after_monitor_blocks_new_entries(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    candidate_id = registry.register(approved_candidate())
    registry.promote(candidate_id, human_approved=True)

    account = PaperAccount(capital=1000.0)
    account.open_position("BTCUSDT", "LONG", 100.0, 2.0, 2.0, "2026-08-25T11:00:00+00:00")
    seed_losses(account, 20)
    loop = PaperExecutionLoop(account, registry)

    result = loop.on_market({
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "price": 101.0,
        "stop_distance": 2.0,
        "rr": 2.0,
        "timestamp": "2026-08-25T12:00:00+00:00",
    }, exit_signal=True)

    assert result["action"] == "CLOSE"
    assert account.position is None


def test_account_snapshot_tracks_loss_streak(tmp_path):
    account = PaperAccount(capital=1000.0)
    seed_losses(account, 4)
    snapshot = snapshot_from_account(account, 100.0)
    assert snapshot["closed_trades"] == 4
    assert snapshot["consecutive_losses"] == 4
    assert snapshot["profit_factor"] == 0.0
