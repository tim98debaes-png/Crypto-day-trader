from optimizer_dashboard import build_signal_strategy_factory, optimize_candles, result_rows


def candles():
    return [
        {"timestamp": f"2026-01-01T00:{i * 2:02d}:00+00:00", "symbol": f"BACKTEST{i}", "close": 100 + i, "long_score": 2.0 if i == 0 else 0.0, "short_score": 2.0 if i == 2 else 0.0, "stop_distance": 1.0}
        for i in range(6)
    ]


def test_signal_factory_emits_normalized_signals():
    strategy = build_signal_strategy_factory()({"signal_threshold": 1.0, "rr": 2.0})
    assert strategy(candles()[0]) == {"action": "LONG", "stop_distance": 1.0, "rr": 2.0}
    assert strategy(candles()[2]) == {"action": "SHORT", "stop_distance": 1.0, "rr": 2.0}
    assert strategy({"long_score": 0, "short_score": 0, "stop_distance": 1})["action"] == "WAIT"


def test_dashboard_optimization_is_serializable_and_ranked():
    rows = optimize_candles(candles(), [0.5, 1.0, 1.5], [1.5, 2.0], top_n=3)
    assert len(rows) == 3
    assert [row["rank"] for row in rows] == [1, 2, 3]
    assert all("signal_threshold" in row and "rr" in row for row in rows)


def test_result_rows_preserves_core_metrics():
    rows = result_rows([])
    assert rows == []
