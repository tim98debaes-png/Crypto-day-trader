"""Phase 31 end-to-end paper-trading validation.

These tests exercise the production path from candidate registry promotion
through signal generation, execution, position management and rollback safety.
"""

from candidate_registry import CandidateRegistry
from paper_engine import PaperAccount
from paper_execution import PaperExecutionLoop
from paper_strategy_runner import PaperStrategyRunner


def candidate(symbol="BTCUSDT", direction="LONG"):
    return {
        "Status": "ROBUST",
        "Coin": symbol,
        "OOS %": 10.0,
        "OOS PF": 1.5,
        "OOS trades": 25,
        "OOS DD": -10.0,
        "Stability": 80.0,
        "MC P05 %": 5.0,
        "Direction": direction,
        "RR": 2.0,
    }


def market(price=100.0, symbol="BTCUSDT", direction="LONG"):
    return {
        "symbol": symbol,
        "direction": direction,
        "price": price,
        "stop_distance": 2.0,
        "rr": 2.0,
        "timestamp": "2026-08-26T08:00:00+00:00",
    }


def test_phase31_registry_to_open_to_close(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    cid = registry.register(candidate())
    assert registry.promote(cid, human_approved=True).approved

    account = PaperAccount(capital=1000, fee_pct=0, slippage_pct=0)
    runner = PaperStrategyRunner(PaperExecutionLoop(account, registry=registry))

    opened = runner.process(
        market(), candidate(),
        {"long_score": 3.0, "short_score": 0.0, "stop_distance": 2.0},
    )
    assert opened["action"] == "OPEN"
    assert opened["candidate_id"] == cid

    closed = runner.process(market(price=104), candidate(), {"long_score": 0, "short_score": 0})
    assert closed["action"] == "CLOSE"
    assert closed["reason"] == "TP"
    assert account.position is None


def test_phase31_deactivation_blocks_new_entry(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    cid = registry.register(candidate())
    registry.promote(cid, human_approved=True)
    registry.deactivate()

    loop = PaperExecutionLoop(PaperAccount(capital=1000), registry=registry)
    result = loop.on_market(market(), candidate=candidate())

    assert result["action"] == "WAIT"
    assert result["reason"] == "no_active_candidate"
    assert loop.account.position is None


def test_phase31_registry_direction_is_authoritative(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    cid = registry.register(candidate(direction="SHORT"))
    registry.promote(cid, human_approved=True)

    loop = PaperExecutionLoop(PaperAccount(capital=1000), registry=registry)
    result = loop.on_market(
        market(direction="LONG"),
        candidate=candidate(direction="LONG"),
    )

    assert result["action"] == "WAIT"
    assert result["reason"] == "candidate_direction_mismatch"
    assert loop.account.position is None
