"""Final Phase 5 paper-trading regression/stress coverage.

These tests remain simulation-only: they exercise the deterministic paper
execution and portfolio layers with synthetic market snapshots.
"""

from paper_engine import PaperAccount
from paper_execution import PaperExecutionLoop
from paper_portfolio import PaperPortfolio
from paper_router import candidate_is_approved, route_candidate


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


def market(symbol="BTCUSDT", direction="LONG", price=100):
    return {
        "symbol": symbol,
        "direction": direction,
        "price": price,
        "stop_distance": 2,
        "rr": 2,
    }


def test_long_tp_then_short_sl_and_repeated_trade_cycle():
    loop = PaperExecutionLoop(PaperAccount(capital=1000, fee_pct=0, slippage_pct=0))
    candidate = approved_candidate()

    assert loop.on_market(market(price=100), candidate)["action"] == "OPEN"
    # Existing position must be managed before considering another signal.
    assert loop.on_market(market(price=101), candidate)["action"] == "HOLD"
    assert loop.on_market(market(price=104), candidate)["reason"] == "TP"

    assert loop.on_market(market(symbol="ETHUSDT", direction="SHORT", price=100), candidate)["action"] == "OPEN"
    assert loop.on_market(market(symbol="ETHUSDT", direction="SHORT", price=102), candidate)["reason"] == "SL"

    summary = loop.summary()
    assert summary["closed_trades"] == 2
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["win_rate_pct"] == 50.0
    assert summary["max_drawdown_pct"] >= 0


def test_quality_gate_blocks_watch_candidate_and_never_opens():
    account = PaperAccount(capital=1000)
    bad = {"Status": "WATCH"}
    assert candidate_is_approved(bad) is False
    result = route_candidate(account, bad, market())
    assert result["action"] == "BLOCK"
    assert account.position is None


def test_portfolio_shares_capital_across_multiple_symbols_and_audits():
    portfolio = PaperPortfolio(capital=1000, coins=["BTCUSDT", "ETHUSDT"], fee_pct=0, slippage_pct=0)
    btc = portfolio.account("BTCUSDT")
    eth = portfolio.account("ETHUSDT")

    assert btc.capital == 500
    assert eth.capital == 500

    btc.open_position("BTCUSDT", "LONG", 100, 2, 2)
    eth.open_position("ETHUSDT", "SHORT", 100, 2, 2)
    assert portfolio.summary({"BTCUSDT": 100, "ETHUSDT": 100})["open_positions"] == 2

    btc.close_position(104, "TP")
    eth.close_position(102, "SL")
    summary = portfolio.summary()
    assert summary["closed_trades"] == 2
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert len(portfolio.audit_log()) >= 4  # OPEN + CLOSE for both symbols


def test_execution_supports_explicit_signal_exit():
    loop = PaperExecutionLoop(PaperAccount(capital=1000, fee_pct=0, slippage_pct=0))
    candidate = approved_candidate()
    loop.on_market(market(price=100), candidate)
    result = loop.on_market(market(price=101), candidate, exit_signal=True)
    assert result["action"] == "CLOSE"
    assert result["reason"] == "SIGNAL"
    assert loop.summary()["closed_trades"] == 1
