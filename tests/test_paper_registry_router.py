from active_candidate_source import get_active_candidate
from candidate_registry import CandidateRegistry
from paper_engine import PaperAccount
from paper_execution import PaperExecutionLoop
from paper_registry_router import on_registry_market


def candidate(coin="BTCUSDT", direction="LONG"):
    return {
        "Status": "ROBUST",
        "Coin": coin,
        "OOS %": 4.0,
        "OOS PF": 1.5,
        "OOS trades": 20,
        "OOS DD": -8.0,
        "Stability": 75,
        "MC P05 %": 2.0,
        "Direction": direction,
        "RR": 2.0,
    }


def make_loop(registry=None):
    account = PaperAccount(
        capital=1000.0,
        risk_pct=1.0,
        fee_pct=0.1,
        slippage_pct=0.0,
    )
    return PaperExecutionLoop(account, registry=registry)


def market(price=100.0, direction="LONG"):
    return {
        "symbol": "BTCUSDT",
        "direction": direction,
        "price": price,
        "stop_distance": 2.0,
        "rr": 2.0,
        "timestamp": "2026-08-25T18:00:00+00:00",
    }


def test_router_blocks_without_active_registry_candidate(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    loop = make_loop(registry)

    result = on_registry_market(loop, registry, market())

    assert result["action"] == "WAIT"
    assert result["reason"] == "no_active_candidate"
    assert loop.account.position is None


def test_router_uses_registry_candidate_and_attaches_id(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    candidate_id = registry.register(candidate())
    decision = registry.promote(candidate_id, human_approved=True)
    assert decision.approved is True

    gate = get_active_candidate(registry, "BTCUSDT")
    assert gate.allowed is True

    loop = make_loop(registry)
    result = on_registry_market(loop, registry, market())

    assert result["action"] == "OPEN"
    assert result["candidate_id"] == candidate_id
    assert loop.account.position is not None


def test_router_blocks_wrong_symbol(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    candidate_id = registry.register(candidate("BTCUSDT"))
    registry.promote(candidate_id, human_approved=True)

    loop = make_loop(registry)
    wrong_market = dict(market())
    wrong_market["symbol"] = "ETHUSDT"

    result = on_registry_market(loop, registry, wrong_market)

    assert result["action"] == "WAIT"
    assert result["reason"] == "candidate_symbol_mismatch"
    assert loop.account.position is None


def test_execution_ignores_conflicting_session_candidate(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    loop = make_loop(registry)

    # This candidate would pass the legacy quality gate, but there is no active
    # registry candidate. It must not authorize a paper entry anymore.
    session_candidate = candidate()
    result = loop.on_market(market(), candidate=session_candidate)

    assert result["action"] == "WAIT"
    assert result["reason"] == "no_active_candidate"
    assert loop.account.position is None


def test_execution_uses_registry_direction_not_session_direction(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    candidate_id = registry.register(candidate(direction="SHORT"))
    registry.promote(candidate_id, human_approved=True)

    loop = make_loop(registry)
    conflicting_market = market(direction="LONG")

    result = loop.on_market(conflicting_market, candidate=candidate(direction="LONG"))

    assert result["action"] == "WAIT"
    assert result["reason"] == "candidate_direction_mismatch"
    assert loop.account.position is None
