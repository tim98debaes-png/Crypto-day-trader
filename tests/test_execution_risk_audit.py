from paper_engine import PaperAccount


def test_close_records_execution_risk_audit():
    account = PaperAccount(capital=1000.0, cash=1000.0, fee_pct=0.0, slippage_pct=0.0)
    position = account.open_position(
        "BTCUSDT", "LONG", 100.0, 1.0, 2.0,
        timestamp="2026-08-28T10:00:00+00:00",
        risk_pct_override=0.5,
        strategy_score=5,
        strategy_tier="A",
    )
    pnl = account.close_position(position.stop_price, reason="SL", timestamp="2026-08-28T10:01:00+00:00")
    event = account.audit_log[-1]
    assert pnl < 0
    assert event["reason"] == "SL"
    assert event["intended_risk_amount"] == position.risk_amount
    assert event["intended_stop_price"] == position.stop_price
    assert event["actual_loss_amount"] == abs(pnl)
    assert event["risk_to_actual_ratio"] == 1.0
    assert event["stop_gap_pct"] == 0.0
