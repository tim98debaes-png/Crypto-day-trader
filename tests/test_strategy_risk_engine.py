import pytest
from paper_engine import PaperAccount
from strategy_risk_controls import RiskConfig


def test_hard_position_cap_and_total_risk_cap():
    cfg = RiskConfig(max_open_positions=2, soft_open_positions=2, max_total_open_risk_pct=1.0)
    account = PaperAccount(capital=1000, risk_pct=0.5, fee_pct=0, slippage_pct=0, risk_config=cfg)
    account.open_position("BTCUSDT", "LONG", 100, 1, 2, timestamp="2026-08-27T10:00:00+00:00")
    account.open_position("ETHUSDT", "LONG", 100, 1, 2, timestamp="2026-08-27T10:01:00+00:00")
    with pytest.raises(RuntimeError):
        account.open_position("SOLUSDT", "LONG", 100, 1, 2, timestamp="2026-08-27T10:02:00+00:00")


def test_loss_streak_halves_risk_after_four_losses():
    account = PaperAccount(capital=1000, risk_pct=0.5, fee_pct=0, slippage_pct=0)
    for i in range(4):
        account.open_position(f"C{i}USDT", "LONG", 100, 1, 1, timestamp=f"2026-08-27T10:{i:02d}:00+00:00")
        account.close_position(99, reason="SL", timestamp=f"2026-08-27T10:{i:02d}:30+00:00", symbol=f"C{i}USDT")
    assert account.loss_streak == 4
    assert account._risk_multiplier("2026-08-27T11:00:00+00:00") == pytest.approx(0.5)


def test_partial_take_profit_moves_stop_to_breakeven():
    account = PaperAccount(capital=1000, risk_pct=0.5, fee_pct=0, slippage_pct=0)
    position = account.open_position("BTCUSDT", "LONG", 100, 2, 2, timestamp="2026-08-27T10:00:00+00:00")
    pnl = account.take_partial_profit("BTCUSDT", 102, timestamp="2026-08-27T10:05:00+00:00")
    assert pnl > 0
    assert position.partial_taken is True
    assert position.quantity == pytest.approx(position.initial_quantity * 0.5)
    assert position.stop_price >= position.entry_price


def test_trailing_stop_only_moves_in_favorable_direction():
    account = PaperAccount(capital=1000, risk_pct=0.5, fee_pct=0, slippage_pct=0)
    position = account.open_position("BTCUSDT", "LONG", 100, 2, 2)
    original = position.stop_price
    account.update_trailing_stop("BTCUSDT", 104, 0.5)
    moved = position.stop_price
    assert moved > original
    account.update_trailing_stop("BTCUSDT", 102, 0.5)
    assert position.stop_price == pytest.approx(moved)
