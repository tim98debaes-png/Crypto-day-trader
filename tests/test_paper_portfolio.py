from paper_portfolio import PaperPortfolio


def test_portfolio_creates_isolated_symbol_accounts():
    portfolio = PaperPortfolio(capital=1000, fee_pct=0, slippage_pct=0)
    btc = portfolio.account("btcusdt")
    eth = portfolio.account("ethusdt")
    assert btc is portfolio.account("BTCUSDT")
    assert eth is portfolio.account("ETHUSDT")
    assert btc is not eth


def test_portfolio_summary_tracks_closed_trade():
    portfolio = PaperPortfolio(capital=1000, fee_pct=0, slippage_pct=0)
    account = portfolio.account("BTCUSDT")
    account.open_position("BTCUSDT", "LONG", 100, 2, 2)
    account.close_position(104, "TP")
    summary = portfolio.summary({"BTCUSDT": 104})
    assert summary["closed_trades"] == 1
    assert summary["wins"] == 1
    assert summary["win_rate_pct"] == 100.0
    assert summary["profit_factor"] > 0
