from research.strategy_benchmark import BenchmarkConfig, evaluate_strategies, rank_results


def test_same_data_and_costs_are_used_for_each_strategy():
    candles = [
        {"timestamp": "2026-01-01T00:00:00+00:00", "symbol": "BTCUSDT", "close": 100},
        {"timestamp": "2026-01-01T00:01:00+00:00", "symbol": "BTCUSDT", "close": 104},
        {"timestamp": "2026-01-01T00:02:00+00:00", "symbol": "BTCUSDT", "close": 104},
    ]
    def winner(_):
        return {"action": "LONG", "stop_distance": 2, "rr": 2}
    def no_trade(_):
        return {"action": "WAIT"}
    results = evaluate_strategies(candles, {"winner": winner, "no_trade": no_trade}, BenchmarkConfig(fee_pct=0, slippage_pct=0))
    assert set(results) == {"winner", "no_trade"}
    assert results["winner"]["closed_trades"] == 1
    assert results["no_trade"]["closed_trades"] == 0


def test_ranker_does_not_call_tiny_samples_validated_edges():
    results = {"two_wins": {"closed_trades": 2, "profit_factor": 99}, "large": {"closed_trades": 30, "profit_factor": 1.2}}
    ranked = rank_results(results)
    assert ranked[0][0] == "large"
    assert ranked[1][1] != ranked[0][1]
