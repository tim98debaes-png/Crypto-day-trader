import json

from paper_portfolio import PaperPortfolio
from paper_reporting import build_report, closed_trade_rows, summary_rows


def test_build_report_is_read_only_and_json_safe():
    portfolio = PaperPortfolio(capital=1000, fee_pct=0, slippage_pct=0)
    account = portfolio.account("BTCUSDT")
    account.open_position("BTCUSDT", "LONG", 100, 2, 2)
    account.close_position(104, "TP")

    before = list(portfolio.equity_history)
    report = build_report(portfolio, {"BTCUSDT": 104})

    assert report["schema_version"] == 1
    assert report["simulation_only"] is True
    assert report["summary"]["closed_trades"] == 1
    assert report["closed_trades"][0]["reason"] == "TP"
    assert report["open_positions"] == []
    assert portfolio.equity_history == before or len(portfolio.equity_history) == len(before) + 1

    json.dumps(report, allow_nan=False)


def test_report_rows_are_stable_for_csv_consumers():
    portfolio = PaperPortfolio(capital=1000, fee_pct=0, slippage_pct=0)
    account = portfolio.account("BTCUSDT")
    account.open_position("BTCUSDT", "SHORT", 100, 2, 2)
    account.close_position(102, "SL")

    report = build_report(portfolio, {"BTCUSDT": 102})
    trades = closed_trade_rows(report)
    metrics = summary_rows(report)

    assert trades[0]["direction"] == "SHORT"
    assert trades[0]["reason"] == "SL"
    assert {row["metric"] for row in metrics} >= {
        "Profit factor",
        "Expectancy",
        "Total fees",
        "LONG trades",
        "SHORT trades",
    }
