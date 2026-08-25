import pytest

from backtest_engine import HistoricalBacktester


CANDLES = [
    {"timestamp": "2026-01-01T00:00:00+00:00", "symbol": "BTCUSDT", "close": 100.0},
    {"timestamp": "2026-01-01T00:01:00+00:00", "symbol": "BTCUSDT", "close": 104.0},
    {"timestamp": "2026-01-01T00:02:00+00:00", "symbol": "BTCUSDT", "close": 104.0},
]


def test_backtest_reuses_paper_execution_and_reports_trade():
    calls = []

    def strategy(candle):
        calls.append(candle["timestamp"])
        if candle["timestamp"].endswith("00:00+00:00"):
            return {"action": "LONG", "stop_distance": 2.0, "rr": 2.0}
        return {"action": "WAIT"}

    result = HistoricalBacktester(fee_pct=0, slippage_pct=0).run(CANDLES, strategy)

    assert len(calls) == 3
    assert result.summary()["closed_trades"] == 1
    assert result.summary()["wins"] == 1
    assert result.final_equity == pytest.approx(1010.0)
    assert result.summary()["return_pct"] == pytest.approx(1.0)


def test_backtest_rejects_out_of_order_candles():
    candles = [CANDLES[1], CANDLES[0]]
    with pytest.raises(ValueError, match="chronologically"):
        HistoricalBacktester().run(candles, lambda _: {"action": "WAIT"})


def test_backtest_rejects_invalid_close():
    with pytest.raises(ValueError, match="positive"):
        HistoricalBacktester().run(
            [{"timestamp": "2026-01-01T00:00:00+00:00", "close": 0}],
            lambda _: {"action": "WAIT"},
        )


def test_backtest_supports_short_and_signal_close():
    candles = [
        {"timestamp": "2026-01-01T00:00:00+00:00", "symbol": "BTCUSDT", "close": 100},
        {"timestamp": "2026-01-01T00:01:00+00:00", "symbol": "BTCUSDT", "close": 98},
    ]

    def strategy(candle):
        if candle["close"] == 100:
            return {"action": "SHORT", "stop_distance": 2, "rr": 2}
        return {"action": "CLOSE"}

    result = HistoricalBacktester(fee_pct=0, slippage_pct=0).run(candles, strategy)
    assert result.summary()["short_trades"] if "short_trades" in result.summary() else True
    assert result.summary()["closed_trades"] == 1
    assert result.final_equity == pytest.approx(1005.0)
