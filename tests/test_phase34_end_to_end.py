"""Phase 34 end-to-end paper-entry safety contract."""

from paper_engine import PaperAccount
from phase34_signal_gate import evaluate_signal_entry


def test_phase34_safe_signal_reaches_paper_engine():
    gate = evaluate_signal_entry(
        paper_mode=True,
        strategy_ready=True,
        heartbeat_age_seconds=5,
        drawdown_pct=0.0,
    )
    assert gate.allowed is True

    account = PaperAccount(capital=1000, fee_pct=0.0, slippage_pct=0.0)
    position = account.open_position("BTCUSDT", "LONG", 100, 2, 2)

    assert position.symbol == "BTCUSDT"
    assert account.position is not None
    assert len(account.audit_log) == 1


def test_phase34_unsafe_signal_never_reaches_paper_engine():
    gate = evaluate_signal_entry(
        paper_mode=True,
        strategy_ready=True,
        heartbeat_age_seconds=301,
        drawdown_pct=0.0,
    )
    assert gate.allowed is False

    account = PaperAccount(capital=1000)
    if gate.allowed:
        account.open_position("BTCUSDT", "LONG", 100, 2, 2)

    assert account.position is None
    assert account.audit_log == []


def test_phase34_multiple_runtime_failures_are_preserved():
    gate = evaluate_signal_entry(
        paper_mode=False,
        strategy_ready=False,
        heartbeat_age_seconds=None,
        drawdown_pct=-25.0,
    )
    assert gate.allowed is False
    assert gate.runtime.reasons == (
        "paper_mode_required",
        "strategy_not_ready",
        "heartbeat_missing",
        "drawdown_limit",
    )
