from candidate_registry import CandidateRegistry


def valid_candidate(label="A"):
    return {
        "Status": "ROBUST",
        "label": label,
        "OOS %": 4.0,
        "OOS PF": 1.5,
        "OOS trades": 20,
        "OOS DD": -8.0,
        "Stability": 75,
        "MC P05 %": 2.0,
    }


def test_register_is_deterministic(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    candidate = valid_candidate()
    first = registry.register(candidate)
    second = registry.register(dict(candidate))
    assert first == second
    assert registry.get(first)["status"] == "REGISTERED"


def test_promotion_requires_human_approval(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    candidate_id = registry.register(valid_candidate())

    blocked = registry.promote(candidate_id)
    assert blocked.status == "BLOCKED"
    assert blocked.reason == "human_approval_required"
    assert registry.active() is None


def test_promotion_activates_candidate(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    candidate_id = registry.register(valid_candidate())

    decision = registry.promote(candidate_id, human_approved=True)
    assert decision.approved
    assert registry.active()["id"] == candidate_id
    assert registry.active()["status"] == "ACTIVE"


def test_new_promotion_rolls_back_previous_active(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    first = registry.register(valid_candidate("A"))
    second = registry.register(valid_candidate("B"))

    registry.promote(first, human_approved=True)
    registry.promote(second, human_approved=True)

    assert registry.active()["id"] == second
    assert registry.get(first)["status"] == "ROLLED_BACK"


def test_explicit_rollback_restores_previous_candidate(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    first = registry.register(valid_candidate("A"))
    second = registry.register(valid_candidate("B"))
    registry.promote(first, human_approved=True)
    registry.promote(second, human_approved=True)

    restored = registry.rollback(first)
    assert restored == first
    assert registry.active()["id"] == first
    assert registry.get(second)["status"] == "ROLLED_BACK"
    assert registry.history()[-1]["event"] == "ROLLBACK"


def test_unknown_candidate_is_safe(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    decision = registry.promote("missing", human_approved=True)
    assert decision.status == "BLOCKED"
    assert decision.reason == "unknown_candidate"
