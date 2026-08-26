"""Phase 31 portfolio safety and multi-asset limit validation."""

import pytest

from paper_portfolio import PaperPortfolio


def candidate():
    return {"Status": "ROBUST", "Strategy Params": {"sl_atr": 2, "rr": 2}}


def test_phase31_rejects_non_positive_capital(tmp_path):
    with pytest.raises(ValueError, match="capital must be positive"):
        PaperPortfolio(capital=0, coins=["BTCUSDT"], persist=False, state_path=str(tmp_path / "s.json"))


def test_phase31_rejects_negative_capital(tmp_path):
    with pytest.raises(ValueError, match="capital must be positive"):
        PaperPortfolio(capital=-100, coins=["BTCUSDT"], persist=False, state_path=str(tmp_path / "s.json"))


def test_phase31_symbol_normalization_and_shared_allocation(tmp_path):
    portfolio = PaperPortfolio(capital=1000, coins=["btcusdt", "ETHUSDT"], persist=False, state_path=str(tmp_path / "s.json"))
    btc = portfolio.account("btcusdt")
    eth = portfolio.account("ethusdt")
    assert portfolio.coins == ["BTCUSDT", "ETHUSDT"]
    assert btc.capital == pytest.approx(500)
    assert eth.capital == pytest.approx(500)


def test_phase31_invalid_risk_parameters_do_not_open(tmp_path):
    portfolio = PaperPortfolio(capital=1000, coins=["BTCUSDT"], persist=False, state_path=str(tmp_path / "s.json"))
    result = portfolio.process("BTCUSDT", candidate(), {"price": 100, "timestamp": "2026-08-26T10:00:00+00:00"}, {"long_score": 2, "short_score": 0, "stop_distance": 0, "rr": 2})
    assert result == {"action": "SKIP", "reason": "invalid_risk_parameters"}
    assert portfolio.account("BTCUSDT").position is None
