import pytest
from strategy_optimizer import StrategyOptimizer

CANDLES = [{"timestamp": f"2026-01-01T00:0{i}:00+00:00", "close": 100 + i} for i in range(6)]

def factory(params):
    threshold = params["threshold"]
    def strategy(candle):
        if candle["close"] == 100 and threshold == 1:
            return {"action": "LONG", "stop_distance": 1, "rr": 2}
        if candle["close"] == 102 and threshold == 2:
            return {"action": "SHORT", "stop_distance": 1, "rr": 2}
        return {"action": "WAIT"}
    return strategy

def test_optimizer_returns_deterministic_ranked_results():
    results = StrategyOptimizer().optimize(CANDLES, {"threshold": [1, 2]}, factory, top_n=2)
    assert len(results) == 2
    assert results[0].score >= results[1].score

def test_optimizer_rejects_invalid_grid():
    with pytest.raises(ValueError): StrategyOptimizer().optimize(CANDLES, {}, factory)
    with pytest.raises(ValueError): StrategyOptimizer().optimize(CANDLES, {"threshold": []}, factory)

def test_walk_forward_keeps_test_data_unseen_during_optimization():
    result = StrategyOptimizer().walk_forward(CANDLES, {"threshold": [1, 2]}, factory, train_ratio=0.5, top_n=2)
    assert result["train_candles"] == 3
    assert result["test_candles"] == 3
    assert len(result["candidates"]) == 2
    assert all("train" in c and "test" in c for c in result["candidates"])

def test_walk_forward_rejects_bad_split():
    with pytest.raises(ValueError): StrategyOptimizer().walk_forward(CANDLES, {"threshold": [1]}, factory, train_ratio=1)
