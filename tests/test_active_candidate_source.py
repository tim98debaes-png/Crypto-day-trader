from active_candidate_source import get_active_candidate
from candidate_registry import CandidateRegistry


def candidate(label="A", coin=None):
    data = {
        "Status": "ROBUST",
        "label": label,
        "OOS %": 4.0,
        "OOS PF": 1.5,
        "OOS trades": 20,
        "OOS DD": -8.0,
        "Stability": 75,
        "MC P05 %": 2.0,
    }
    if coin:
        data["Coin"] = coin
    return data


def test_no_active_candidate_is_blocked(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")

    result = get_active_candidate(registry)

    assert result.allowed is False
    assert result.reason == "no_active_candidate"
    assert result.active is None


def test_active_candidate_is_read_only_and_approved(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    candidate_id = registry.register(candidate(coin="BTCUSDT"))
    decision = registry.promote(candidate_id, human_approved=True)

    assert decision.approved is True

    result = get_active_candidate(registry, "BTCUSDT")

    assert result.allowed is True
    assert result.reason == "active_candidate_approved"
    assert result.active.candidate_id == candidate_id
    assert result.active.candidate["Coin"] == "BTCUSDT"

    # The source must not mutate registry state.
    assert registry.active()["id"] == candidate_id
    assert registry.active()["status"] == "ACTIVE"


def test_symbol_mismatch_is_blocked(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    candidate_id = registry.register(candidate(coin="BTCUSDT"))
    registry.promote(candidate_id, human_approved=True)

    result = get_active_candidate(registry, "ETHUSDT")

    assert result.allowed is False
    assert result.reason == "candidate_symbol_mismatch"
    assert result.active is None


def test_failed_quality_gate_is_blocked_even_when_active(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    weak = candidate(coin="BTCUSDT")
    weak["OOS PF"] = 1.05
    candidate_id = registry.register(weak)

    # Registry promotion itself blocks weak candidates, so this test simulates
    # a stale/corrupt ACTIVE entry without using promotion to bypass the gate.
    data = registry._load()
    data["candidates"][candidate_id]["status"] = "ACTIVE"
    data["active_id"] = candidate_id
    registry._save(data)

    result = get_active_candidate(registry, "BTCUSDT")

    assert result.allowed is False
    assert result.reason == "quality_gates_failed"
