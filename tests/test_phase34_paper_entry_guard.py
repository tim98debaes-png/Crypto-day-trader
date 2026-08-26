import pytest

from paper_engine import PaperAccount


def test_paper_entry_is_allowed_when_runtime_state_is_safe():
    account = PaperAccount(capital=1000, fee_pct=0.0, slippage_pct=0.0)

    position = account.open_position(
        "BTCUSDT",
        "LONG",
        price=100,
        stop_distance=2,
        rr=2,
        strategy_ready=True,
        heartbeat_age_seconds=10,
        paper_mode=True,
    )

    assert position.symbol == "BTCUSDT"
    assert len(account.audit_log) == 1


def test_paper_entry_fails_closed_on_stale_heartbeat_without_mutating_state():
    account = PaperAccount(capital=1000)

    with pytest.raises(RuntimeError, match="heartbeat_stale"):
        account.open_position(
            "BTCUSDT",
            "LONG",
            price=100,
            stop_distance=2,
            rr=2,
            strategy_ready=True,
            heartbeat_age_seconds=301,
            paper_mode=True,
        )

    assert account.position is None
    assert account.audit_log == []


def test_paper_entry_fails_closed_when_not_in_paper_mode():
    account = PaperAccount(capital=1000)

    with pytest.raises(RuntimeError, match="paper_mode_required"):
        account.open_position(
            "BTCUSDT",
            "LONG",
            price=100,
            stop_distance=2,
            rr=2,
            strategy_ready=True,
            heartbeat_age_seconds=10,
            paper_mode=False,
        )

    assert account.position is None
    assert account.audit_log == []
