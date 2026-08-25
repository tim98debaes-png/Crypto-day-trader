from final_validation import final_validation


def evidence():
    return {
        "ci_green": True,
        "paper_validation_green": True,
        "safety_gate_green": True,
        "reconciliation_green": True,
        "sandbox_green": True,
        "operational_hardening_green": True,
        "secrets_absent": True,
        "live_disabled": True,
    }


def test_complete_evidence_is_go():
    result = final_validation(evidence())
    assert result.go is True
    assert result.blockers == ()


def test_missing_evidence_is_no_go():
    result = final_validation({"ci_green": True})
    assert result.go is False
    assert "paper_validation_green" in result.blockers


def test_live_enabled_is_never_a_final_go():
    data = evidence(); data["live_disabled"] = False
    result = final_validation(data)
    assert result.go is False
    assert result.blockers == ("live_disabled",)
