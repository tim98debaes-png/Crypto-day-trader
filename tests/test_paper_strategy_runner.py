from paper_engine import PaperAccount
from paper_execution import PaperExecutionLoop
from paper_strategy_runner import PaperStrategyRunner


def candidate():
    return {
        "Status": "ROBUST",
        "Stability": 75,
        "OOS PF": 1.5,
        "OOS %": 10,
        "OOS trades": 20,
        "OOS DD": -8,
        "MC P05 %": -2,
        "signal_threshold": 2,
        "rr": 2,
    }


def test_strategy_runner_opens_from_confirmed_long_signal():
    runner = PaperStrategyRunner(PaperExecutionLoop(PaperAccount(fee_pct=0, slippage_pct=0)))
    result = runner.process(
        {"symbol": "BTCUSDT", "price": 100},
        candidate(),
        {"long_score": 3, "short_score": 1, "stop_distance": 2},
    )
    assert result["action"] == "OPEN"
    assert result["position"].direction == "LONG"


def test_strategy_runner_does_not_trade_without_confirmation():
    runner = PaperStrategyRunner(PaperExecutionLoop(PaperAccount()))
    result = runner.process(
        {"symbol": "BTCUSDT", "price": 100},
        candidate(),
        {"long_score": 1, "short_score": 1, "stop_distance": 2},
    )
    assert result["action"] == "WAIT"
