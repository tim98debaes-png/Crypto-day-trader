from active_candidate_source import get_active_candidate
from candidate_registry import CandidateRegistry
from paper_engine import PaperAccount
from paper_execution import PaperExecutionLoop
from paper_registry_router import on_registry_market


def candidate(coin="BTCUSDT"):
    return {
        "Status": "ROBUST",
        "Coin": coin,
        "OOS %": 4.0,
        "OOS PF": 1.5,
        "OOS trades": 20,
        "OOS DD": -8.0,
        "Stability": 75,
        "MC P05 %": 2.0,
        "Direction": "LONG",
        "RR": 2.0,
    }


def make_loop():
    account = PaperAccount(
        capital=1000.0,
        risk_pct=1.0,
        fee_pct=0.1,
        slippage_pct=0.0,
    )
    return PaperExecutionLoop(account)


def market(price=100.0):
    return {
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "price": price,
        "stop_distance": 2.0,
        "rr": 2.0,
        "timestamp": "2026-08-25T18:00:00+00:00",
    }


def test_router_blocks_without_active_registry_candidate(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    loop = make_loop()

    result = on_registry_market(loop, registry, market())

    assert result["action"] == "WAIT"
    assert loop.account.position is None


def test_router_uses_registry_candidate_and_attaches_id(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    candidate_id = registry.register(candidate())
    decision = registry.promote(candidate_id, human_approved=True)
    assert decision.approved is True

    gate = get_active_candidate(registry, "BTCUSDT")
    assert gate.allowed is True

    loop = make_loop()
    result = on_registry_market(loop, registry, market())

    assert result["action"] == "OPEN"
    assert loop.account.position is not None


def test_router_blocks_wrong_symbol(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    candidate_id = registry.register(candidate("BTCUSDT"))
    registry.promote(candidate_id, human_approved=True)

    loop = make_loop()
    wrong_market = dict(market())
    wrong_market["symbol"] = "ETHUSDT"

    result = on_registry_market(loop, registry, wrong_market)

    assert result["action"] == "WAIT"
    assert loop.account.position is None
