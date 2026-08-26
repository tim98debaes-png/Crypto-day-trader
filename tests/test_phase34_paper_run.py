"""Deterministic end-to-end paper trading session for Phase 34."""

from candidate_registry import CandidateRegistry
from paper_engine import PaperAccount
from paper_execution import PaperExecutionLoop


def _registry(tmp_path):
    registry = CandidateRegistry(tmp_path / "candidate_registry.json")
    candidate = {
        "Status": "ROBUST",
        "Stability": 75,
        "OOS PF": 1.5,
        "OOS %": 12,
        "OOS trades": 20,
        "OOS DD": -8,
        "MC P05 %": -2,
        "Direction": "LONG",
        "RR": 2.0,
        "symbol": "BTCUSDT",
    }
    candidate_id = registry.register(candidate)
    decision = registry.promote(candidate_id, human_approved=True)
    assert decision.approved is True
    assert registry.active() is not None
    return registry


def test_phase34_complete_paper_session_open_hold_close(tmp_path):
    account = PaperAccount(capital=1000, fee_pct=0.0, slippage_pct=0.0)
    loop = PaperExecutionLoop(account, registry=_registry(tmp_path), persist_observability=False)

    opened = loop.on_market({
        "symbol": "BTCUSDT", "price": 100.0, "stop_distance": 2.0,
        "direction": "LONG", "timestamp": "2026-01-01T00:00:00Z",
    })
    assert opened["action"] == "OPEN"
    assert account.position is not None

    held = loop.on_market({
        "symbol": "BTCUSDT", "price": 101.0,
        "direction": "LONG", "timestamp": "2026-01-01T00:01:00Z",
    })
    assert held["action"] == "HOLD"

    closed = loop.on_market({
        "symbol": "BTCUSDT", "price": 104.0,
        "direction": "LONG", "timestamp": "2026-01-01T00:02:00Z",
    })
    assert closed["action"] == "CLOSE"
    assert closed["reason"] == "TP"
    assert account.position is None
    assert loop.stats.closed_trades == 1
    assert loop.stats.wins == 1
    assert loop.stats.losses == 0
    assert account.equity(104.0) > account.capital


def test_phase34_unsafe_signal_never_reaches_paper_engine():
    from phase34_signal_gate import evaluate_signal_entry

    decision = evaluate_signal_entry(
        paper_mode=True,
        strategy_ready=True,
        heartbeat_age_seconds=301,
        drawdown_pct=0.0,
    )
    assert decision.allowed is False

    account = PaperAccount(capital=1000)
    if decision.allowed:
        account.open_position("BTCUSDT", "LONG", 100, 2, 2)

    assert account.position is None
    assert account.audit_log == []
