"""Deterministic end-to-end paper trading session for Phase 34."""

from paper_engine import PaperAccount
from paper_execution import PaperExecutionLoop
from candidate_registry import CandidateRegistry


def _registry():
    registry = CandidateRegistry()
    registry.register({
        "id": "phase34-e2e",
        "status": "ACTIVE",
        "Direction": "LONG",
        "RR": 2.0,
        "symbol": "BTCUSDT",
    })
    return registry


def test_phase34_complete_paper_session_open_hold_close():
    account = PaperAccount(capital=1000, fee_pct=0.0, slippage_pct=0.0)
    loop = PaperExecutionLoop(account, registry=_registry(), persist_observability=False)

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
