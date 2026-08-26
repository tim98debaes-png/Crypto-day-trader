from phase34_signal_gate import evaluate_signal_entry


def test_signal_gate_allows_healthy_paper_runtime():
    decision = evaluate_signal_entry(
        paper_mode=True,
        strategy_ready=True,
        heartbeat_age_seconds=10,
        drawdown_pct=-1.0,
    )
    assert decision.allowed is True
    assert decision.reason == "allowed"


def test_signal_gate_fails_closed_before_execution():
    decision = evaluate_signal_entry(
        paper_mode=True,
        strategy_ready=True,
        heartbeat_age_seconds=301,
        drawdown_pct=-1.0,
    )
    assert decision.allowed is False
    assert decision.reason == "heartbeat_stale"


def test_signal_gate_blocks_non_paper_mode():
    decision = evaluate_signal_entry(
        paper_mode=False,
        strategy_ready=True,
        heartbeat_age_seconds=10,
    )
    assert decision.allowed is False
    assert decision.reason == "paper_mode_required"
