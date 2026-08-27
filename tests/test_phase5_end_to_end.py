from paper_engine import PaperAccount
from paper_execution import PaperExecutionLoop
from paper_portfolio import PaperPortfolio
from paper_router import candidate_is_approved


def approved_candidate():
    return {
        "Status": "TRADE",
        "OOS %": 10,
        "OOS PF": 1.5,
        "OOS trades": 25,
        "OOS DD": -10,
        "Stability": 80,
        "MC P05 %": 5,
    }


def market(price, timestamp):
    return {
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "price": price,
        "stop_distance": 2,
        "rr": 2,
        "timestamp": timestamp,
    }


def test_phase5_end_to_end_signal_entry_exit_portfolio_audit():
    candidate = approved_candidate()
    assert candidate_is_approved(candidate)

    portfolio = PaperPortfolio(capital=1000, coins=["BTCUSDT"], fee_pct=0, slippage_pct=0)
    account = portfolio.account("BTCUSDT")
    loop = PaperExecutionLoop(account)

    opened = loop.on_market(market(100, "2026-08-24T20:00:00Z"), candidate)
    assert opened["action"] == "OPEN"
    assert account.position is not None
    assert account.position.symbol == "BTCUSDT"

    held = loop.on_market(market(101, "2026-08-24T20:05:00Z"))
    assert held["action"] == "HOLD"
    assert portfolio.summary({"BTCUSDT": 101})["open_positions"] == 1

    closed = loop.on_market(market(104, "2026-08-24T20:10:00Z"))
    assert closed["action"] == "CLOSE"
    assert closed["reason"] == "TP"
    assert account.position is None

    summary = portfolio.summary({"BTCUSDT": 104})
    assert summary["symbols"] == 1
    assert summary["closed_trades"] == 1
    assert summary["wins"] == 1
    assert summary["win_rate_pct"] == 100.0
    assert summary["profit_factor"] > 0

    audit = portfolio.audit_log()
    assert [event["event"] for event in audit] == ["OPEN", "PARTIAL_CLOSE", "CLOSE"]
    assert audit[-1]["reason"] == "TP"
    assert float(audit[-1]["pnl"]) > 0
