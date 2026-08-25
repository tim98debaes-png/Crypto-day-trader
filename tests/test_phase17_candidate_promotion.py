from candidate_promotion import promote_candidate, promotion_candidate


def valid_candidate():
    return {
        "parameters": {"signal_threshold": 1.5, "rr": 2.0},
        "test": {
            "return_pct": 8.0,
            "profit_factor": 1.8,
            "closed_trades": 30,
            "max_drawdown_pct": 8.0,
        },
        "Stability": 75.0,
        "MC P05 %": 2.0,
        "Status": "ROBUST",
    }


def test_promotion_requires_explicit_human_approval():
    decision = promote_candidate(valid_candidate())
    assert decision.status == "BLOCKED"
    assert decision.reason == "human_approval_required"


def test_promotion_requires_all_validation_metrics():
    candidate = valid_candidate()
    candidate.pop("MC P05 %")
    decision = promote_candidate(candidate, human_approved=True)
    assert decision.status == "BLOCKED"
    assert decision.reason == "missing_validation_metrics"


def test_promotion_blocks_failed_quality_gate():
    candidate = valid_candidate()
    candidate["test"]["profit_factor"] = 0.9
    decision = promote_candidate(candidate, human_approved=True)
    assert decision.status == "BLOCKED"
    assert decision.reason == "quality_gates_failed"


def test_promotion_succeeds_only_when_all_gates_pass():
    decision = promote_candidate(valid_candidate(), human_approved=True)
    assert decision.status == "PROMOTED"
    assert decision.reason == "all_gates_passed"
    assert decision.approved is True
    assert decision.promoted_at


def test_walk_forward_candidate_is_normalized_to_router_contract():
    normalized = promotion_candidate(valid_candidate())
    assert normalized["OOS %"] == 8.0
    assert normalized["OOS PF"] == 1.8
    assert normalized["OOS trades"] == 30
    assert normalized["OOS DD"] == -8.0
    assert normalized["Stability"] == 75.0
    assert normalized["MC P05 %"] == 2.0
