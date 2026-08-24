from paper_portfolio import PaperPortfolio


def candidate():
    return {
        "Status": "ROBUST",
        "OOS PF": 1.5,
        "OOS %": 8.0,
        "OOS trades": 20,
        "OOS DD": -10.0,
        "Stability": 75.0,
        "MC P05 %": -2.0,
        "Direction": "LONG",
        "Strategy Params": {
            "family": "trend",
            "threshold": 2,
            "rr": 2,
            "sl_atr": 1,
        },
    }


def test_portfolio_processes_approved_candidate():
    portfolio = PaperPortfolio(total_capital=1000, coins=["BTCUSDT"])
    result = portfolio.process(
        "BTCUSDT",
        candidate(),
        {"symbol": "BTCUSDT", "price": 100, "timestamp": "2026-08-24T19:00:00+00:00"},
        {"long_score": 3, "short_score": 0, "stop_distance": 2, "rr": 2},
    )
    assert result["action"] == "OPEN"
    assert portfolio.rows()[0]["Position"].startswith("LONG")


def test_portfolio_tracks_closed_trade():
    portfolio = PaperPortfolio(total_capital=1000, coins=["BTCUSDT"])
    portfolio.process(
        "BTCUSDT", candidate(),
        {"symbol": "BTCUSDT", "price": 100},
        {"long_score": 3, "short_score": 0, "stop_distance": 2, "rr": 2},
    )
    portfolio.process(
        "BTCUSDT", candidate(),
        {"symbol": "BTCUSDT", "price": 104},
        {"long_score": 0, "short_score": 0, "stop_distance": 2, "rr": 2},
    )
    assert portfolio.totals()["closed_trades"] == 1
    assert portfolio.totals()["win_rate_pct"] == 100.0
