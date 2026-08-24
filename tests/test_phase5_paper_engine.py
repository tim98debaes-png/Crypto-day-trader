import pytest

from paper_engine import PaperAccount


def test_long_position_sizes_from_risk_and_closes_with_fees_and_slippage():
    account = PaperAccount(
        capital=1000,
        risk_pct=1,
        fee_pct=0.1,
        slippage_pct=0.0,
    )
    position = account.open_position(
        "BTCUSDT",
        "LONG",
        price=100,
        stop_distance=2,
        rr=2,
        timestamp="2026-08-23T10:00:00+00:00",
    )

    assert position.quantity == pytest.approx(5.0)
    assert position.stop_price == pytest.approx(98.0)
    assert position.target_price == pytest.approx(104.0)

    pnl = account.close_position(
        104,
        reason="TP",
        timestamp="2026-08-23T10:10:00+00:00",
    )
    assert pnl == pytest.approx(19.3)
    assert account.position is None
    assert account.cash == pytest.approx(1019.3)


def test_short_position_has_correct_directional_pnl():
    account = PaperAccount(
        capital=1000,
        risk_pct=1,
        fee_pct=0.0,
        slippage_pct=0.0,
    )
    account.open_position(
        "ETHUSDT",
        "SHORT",
        price=100,
        stop_distance=2,
        rr=2,
    )
    pnl = account.close_position(96, reason="TP")
    assert pnl == pytest.approx(20.0)


def test_daily_loss_guard_blocks_new_position():
    account = PaperAccount(
        capital=1000,
        risk_pct=10,
        fee_pct=0.0,
        slippage_pct=0.0,
        max_daily_loss_pct=3.0,
    )
    account.open_position("BTCUSDT", "LONG", 100, 10, 1)
    account.close_position(96, reason="SL")

    assert account.daily_loss_pct() == pytest.approx(-4.0)
    with pytest.raises(RuntimeError, match="not allowed"):
        account.open_position("BTCUSDT", "LONG", 100, 2, 2)


def test_audit_log_records_open_and_close():
    account = PaperAccount(capital=1000)
    account.open_position("SOLUSDT", "LONG", 100, 2, 2)
    account.close_position(102, reason="TP")

    assert [event["event"] for event in account.audit_log] == ["OPEN", "CLOSE"]
    assert account.audit_log[-1]["reason"] == "TP"
