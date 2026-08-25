from paper_portfolio import PaperPortfolio


def test_portfolio_tracks_return_and_drawdown():
    portfolio = PaperPortfolio(capital=1000, fee_pct=0, slippage_pct=0)
    account = portfolio.account("BTCUSDT")

    account.open_position("BTCUSDT", "LONG", 100, 2, 2)
    portfolio.equity({"BTCUSDT": 101})
    account.close_position(104, "TP")
    summary = portfolio.summary({"BTCUSDT": 104})

    assert summary["return_pct"] == 1.0
    assert summary["peak_equity"] == 1010.0
    assert summary["current_drawdown_pct"] == 0.0
    assert summary["max_drawdown_pct"] == 0.0
    assert summary["avg_trade"] == 10.0
    assert summary["best_trade"] == 10.0
    assert summary["worst_trade"] == 10.0


def test_portfolio_reports_drawdown_after_loss():
    portfolio = PaperPortfolio(capital=1000, fee_pct=0, slippage_pct=0)
    account = portfolio.account("BTCUSDT")

    account.open_position("BTCUSDT", "LONG", 100, 2, 2)
    portfolio.equity({"BTCUSDT": 98})
    account.close_position(98, "SL")
    summary = portfolio.summary({"BTCUSDT": 98})

    assert summary["return_pct"] == -0.5
    assert summary["peak_equity"] == 1000.0
    assert summary["current_drawdown_pct"] == 0.5
    assert summary["max_drawdown_pct"] >= 0.5
    assert summary["losses"] == 1
    assert summary["worst_trade"] == -5.0


def test_portfolio_exposes_detailed_trade_metrics():
    portfolio = PaperPortfolio(capital=1000, fee_pct=0, slippage_pct=0)
    account = portfolio.account("BTCUSDT")

    account.open_position("BTCUSDT", "LONG", 100, 2, 2)
    account.close_position(104, "TP")
    account.open_position("BTCUSDT", "SHORT", 100, 2, 2)
    account.close_position(102, "SL")
    summary = portfolio.summary({"BTCUSDT": 102})

    assert summary["closed_trades"] == 2
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["long_trades"] == 1
    assert summary["short_trades"] == 1
    assert summary["gross_profit"] == 10.0
    # Position sizing is based on current cash, so after the first +€10
    # trade the second trade risks €5.05 rather than the original €5.00.
    assert summary["gross_loss"] == 5.05
    assert summary["total_fees"] == 0.0
    assert summary["expectancy"] == 2.475
    assert summary["payoff_ratio"] == 1.9801980198
    assert summary["profit_factor"] == 1.9801980198
    assert summary["win_rate_pct"] == 50.0
