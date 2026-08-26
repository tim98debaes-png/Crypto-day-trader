"""Phase 34 runtime safety guard tests."""

from phase34_runtime_guard import evaluate_entry_guard


def test_paper_entry_is_allowed_when_all_runtime_gates_are_healthy():
    decision = evaluate_entry_guard(
        paper_mode=True,
        strategy_ready=True,
        heartbeat_age_seconds=10,
        drawdown_pct=-2.0,
    )

    assert decision.allowed is True
    assert decision.reasons == ()


def test_guard_fails_closed_for_non_paper_mode_and_unhealthy_runtime():
    decision = evaluate_entry_guard(
        paper_mode=False,
        strategy_ready=False,
        heartbeat_age_seconds=301,
        drawdown_pct=-25.0,
    )

    assert decision.allowed is False
    assert decision.reasons == (
        "paper_mode_required",
        "strategy_not_ready",
        "heartbeat_stale",
        "drawdown_limit",
    )


def test_missing_heartbeat_blocks_entry():
    decision = evaluate_entry_guard(
        paper_mode=True,
        strategy_ready=True,
        heartbeat_age_seconds=None,
    )

    assert decision.allowed is False
    assert decision.reasons == ("heartbeat_missing",)
