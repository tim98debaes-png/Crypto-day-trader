from paper_engine import PaperAccount
from paper_execution import PaperExecutionLoop


def candidate():
    return {
        "Status": "TRADE",
        "OOS %": 10,
        "OOS PF": 1.5,
        "OOS trades": 25,
        "OOS DD": -10,
        "Stability": 80,
        "MC P05 %": 5,
    }


def market(price):
    return {
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "price": price,
        "stop_distance": 2,
        "rr": 2,
    }


def test_execution_loop_opens_and_closes_at_target():
    loop = PaperExecutionLoop(PaperAccount(capital=1000, fee_pct=0, slippage_pct=0))
    assert loop.on_market(market(100), candidate())["action"] == "OPEN"
    result = loop.on_market(market(104))
    assert result["action"] == "CLOSE"
    assert result["reason"] == "TP"
    summary = loop.summary()
    assert summary["closed_trades"] == 1
    assert summary["wins"] == 1
    assert summary["win_rate_pct"] == 100.0
    assert summary["profit_factor"] > 0


def test_execution_loop_closes_at_stop():
    loop = PaperExecutionLoop(PaperAccount(capital=1000, fee_pct=0, slippage_pct=0))
    loop.on_market(market(100), candidate())
    result = loop.on_market(market(98))
    assert result["action"] == "CLOSE"
    assert result["reason"] == "SL"
    assert loop.summary()["losses"] == 1


def test_execution_loop_waits_for_unapproved_candidate():
    loop = PaperExecutionLoop(PaperAccount(capital=1000))
    result = loop.on_market(market(100), {"Status": "WATCH"})
    assert result["action"] == "WAIT"
    assert loop.account.position is None
