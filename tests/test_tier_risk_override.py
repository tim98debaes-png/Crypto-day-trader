from paper_engine import PaperAccount


def test_tier_b_risk_override_is_applied_and_audit_logged():
    account = PaperAccount(capital=1000.0, cash=1000.0)
    position = account.open_position(
        symbol="TESTUSDT",
        direction="LONG",
        price=100.0,
        stop_distance=1.0,
        rr=2.0,
        risk_pct_override=0.25,
        strategy_score=3,
        strategy_tier="B",
    )
    assert position.risk_amount == 2.5
    assert account.open_risk_pct() == 0.25
    event = account.audit_log[-1]
    assert event["risk_pct"] == 0.25
    assert event["strategy_score"] == 3
    assert event["strategy_tier"] == "B"


def test_tier_a_uses_normal_research_risk_when_no_override():
    account = PaperAccount(capital=1000.0, cash=1000.0)
    position = account.open_position(
        symbol="TESTUSDT",
        direction="LONG",
        price=100.0,
        stop_distance=1.0,
        rr=2.0,
        strategy_score=4,
        strategy_tier="A",
    )
    assert position.risk_amount == 5.0
    assert account.open_risk_pct() == 0.5
