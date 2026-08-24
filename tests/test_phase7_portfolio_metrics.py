from paper_portfolio import PaperPortfolio


def test_portfolio_tracks_return_and_drawdown():
    portfolio = PaperPortfolio(capital=1000, fee_pct=0, slippage_pct=0)
    account = portfolio.account("BTCUSDT")

    account.open_position("BTCUSDT", "LONG", 100, 2, 2)
    portfolio.equity({"BTCUSDT": 101})
    account.close_position(104, "TP")
    summary = portfolio.summary({"BTCUSDT": 104})

    assert summary["return_pct"] == 0.8
    assert summary["peak_equity"] == 1008.0
    assert summary["current_drawdown_pct"] == 0.0
    assert summary["max_drawdown_pct"] == 0.0
    assert summary["avg_trade"] == 8.0
    assert summary["best_trade"] == 8.0
    assert summary["worst_trade"] == 8.0


def test_portfolio_reports_drawdown_after_loss():
    portfolio = PaperPortfolio(capital=1000, fee_pct=0, slippage_pct=0)
    account = portfolio.account("BTCUSDT")

    account.open_position("BTCUSDT", "LONG", 100, 2, 2)
    portfolio.equity({"BTCUSDT": 98})
    account.close_position(98, "SL")
    summary = portfolio.summary({"BTCUSDT": 98})

    assert summary["return_pct"] == -1.0
    assert summary["peak_equity"] == 1000.0
    assert summary["current_drawdown_pct"] == 1.0
    assert summary["max_drawdown_pct"] >= 1.0
    assert summary["losses"] == 1
    assert summary["worst_trade"] == -2.0
