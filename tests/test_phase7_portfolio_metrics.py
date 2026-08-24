from paper_portfolio import PaperPortfolio


def test_portfolio_tracks_return_and_peak_equity():
    portfolio = PaperPortfolio(capital=1000, fee_pct=0, slippage_pct=0)
    account = portfolio.account("BTCUSDT")

    account.open_position("BTCUSDT", "LONG", 100, 2, 2)
    portfolio.summary({"BTCUSDT": 104})
    summary = portfolio.summary({"BTCUSDT": 104})

    assert summary["equity"] > 1000
    assert summary["return_pct"] > 0
    assert summary["peak_equity"] == summary["equity"]
    assert summary["max_drawdown_pct"] == 0


def test_portfolio_drawdown_survives_recovery():
    portfolio = PaperPortfolio(capital=1000, fee_pct=0, slippage_pct=0)
    account = portfolio.account("BTCUSDT")

    account.open_position("BTCUSDT", "LONG", 100, 10, 2)
    portfolio.summary({"BTCUSDT": 90})
    low = portfolio.summary({"BTCUSDT": 90})
    portfolio.summary({"BTCUSDT": 105})
    recovered = portfolio.summary({"BTCUSDT": 105})

    assert low["max_drawdown_pct"] > 0
    assert recovered["max_drawdown_pct"] == low["max_drawdown_pct"]
    assert recovered["peak_equity"] == recovered["equity"]
