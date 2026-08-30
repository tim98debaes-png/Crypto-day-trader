from multi_position_backtest import MultiPositionBacktester


def _run(rows, signal):
    return MultiPositionBacktester(risk_pct=0.5, slippage_pct=0).run(rows, signal)


def _long_on_first(row):
    return {"action": "LONG", "stop_distance": 2.0, "rr": 2.0} if row["timestamp"].endswith("00:00:00+00:00") else {"action": "WAIT"}


def test_entry_is_next_candle_open_not_signal_candle_close():
    rows = [
        {"timestamp": "2026-01-01T00:00:00+00:00", "symbol": "AAA", "open": 100, "high": 120, "low": 90, "close": 101},
        {"timestamp": "2026-01-01T00:01:00+00:00", "symbol": "AAA", "open": 110, "high": 111, "low": 109, "close": 110.5},
    ]
    result = _run(rows, _long_on_first)
    opens = [e for e in result.trades if e.get("event") == "OPEN"]
    assert len(opens) == 1
    assert opens[0]["timestamp"] == rows[1]["timestamp"]
    assert opens[0]["price"] == rows[1]["open"]


def test_signal_close_is_next_candle_open():
    rows = [
        {"timestamp": "2026-01-01T00:00:00+00:00", "symbol": "AAA", "open": 100, "high": 100, "low": 100, "close": 100},
        {"timestamp": "2026-01-01T00:01:00+00:00", "symbol": "AAA", "open": 105, "high": 106, "low": 104, "close": 105},
        {"timestamp": "2026-01-01T00:02:00+00:00", "symbol": "AAA", "open": 120, "high": 121, "low": 119, "close": 120},
        {"timestamp": "2026-01-01T00:03:00+00:00", "symbol": "AAA", "open": 130, "high": 131, "low": 129, "close": 130},
    ]

    def signal(row):
        if row["timestamp"].endswith("00:00:00+00:00"):
            return {"action": "LONG", "stop_distance": 20, "rr": 5}
        if row["timestamp"].endswith("00:02:00+00:00"):
            return {"action": "CLOSE"}
        return {"action": "WAIT"}

    result = _run(rows, signal)
    closes = [e for e in result.trades if e.get("event") == "CLOSE" and e.get("reason") == "SIGNAL"]
    assert len(closes) == 1
    assert closes[0]["timestamp"] == rows[3]["timestamp"]
    assert closes[0]["price"] == rows[3]["open"]


def test_final_candle_signal_is_not_executed():
    rows = [
        {"timestamp": "2026-01-01T00:00:00+00:00", "symbol": "AAA", "open": 100, "high": 101, "low": 99, "close": 100},
    ]
    result = _run(rows, lambda row: {"action": "LONG", "stop_distance": 1, "rr": 2})
    assert not [e for e in result.trades if e.get("event") == "OPEN"]


def test_intrabar_stop_uses_stop_price_when_touched_after_open():
    rows = [
        {"timestamp": "2026-01-01T00:00:00+00:00", "symbol": "AAA", "open": 100, "high": 100, "low": 100, "close": 100},
        {"timestamp": "2026-01-01T00:01:00+00:00", "symbol": "AAA", "open": 100, "high": 101, "low": 97, "close": 100},
    ]
    result = _run(rows, _long_on_first)
    closes = [e for e in result.trades if e.get("event") == "CLOSE"]
    assert closes[0]["reason"] == "SL"
    assert closes[0]["price"] == 98


def test_gap_through_stop_executes_at_next_open():
    rows = [
        {"timestamp": "2026-01-01T00:00:00+00:00", "symbol": "AAA", "open": 100, "high": 100, "low": 100, "close": 100},
        {"timestamp": "2026-01-01T00:01:00+00:00", "symbol": "AAA", "open": 95, "high": 96, "low": 94, "close": 95},
    ]
    result = _run(rows, lambda row: {"action": "LONG", "stop_distance": 2, "rr": 2} if row["timestamp"].endswith("00:00:00+00:00") else {"action": "WAIT"})
    closes = [e for e in result.trades if e.get("event") == "CLOSE"]
    assert closes[0]["reason"] == "SL"
    assert closes[0]["price"] == 95


def test_gap_through_target_executes_at_next_open():
    rows = [
        {"timestamp": "2026-01-01T00:00:00+00:00", "symbol": "AAA", "open": 100, "high": 100, "low": 100, "close": 100},
        {"timestamp": "2026-01-01T00:01:00+00:00", "symbol": "AAA", "open": 105, "high": 106, "low": 104, "close": 105},
    ]
    result = _run(rows, lambda row: {"action": "LONG", "stop_distance": 2, "rr": 2} if row["timestamp"].endswith("00:00:00+00:00") else {"action": "WAIT"})
    closes = [e for e in result.trades if e.get("event") == "CLOSE"]
    assert closes[0]["reason"] == "TP"
    assert closes[0]["price"] == 105


def test_future_candle_range_cannot_change_entry_decision_or_price():
    base = [
        {"timestamp": "2026-01-01T00:00:00+00:00", "symbol": "AAA", "open": 100, "high": 101, "low": 99, "close": 100},
        {"timestamp": "2026-01-01T00:01:00+00:00", "symbol": "AAA", "open": 110, "high": 111, "low": 109, "close": 110},
    ]
    altered_future = [dict(base[0]), dict(base[1], high=1000, low=1, close=999)]

    def signal(row):
        return {"action": "LONG", "stop_distance": 50, "rr": 2} if row["timestamp"].endswith("00:00:00+00:00") else {"action": "WAIT"}

    first = [e for e in _run(base, signal).trades if e.get("event") == "OPEN"]
    second = [e for e in _run(altered_future, signal).trades if e.get("event") == "OPEN"]
    assert first[0]["timestamp"] == second[0]["timestamp"] == base[1]["timestamp"]
    assert first[0]["price"] == second[0]["price"] == base[1]["open"]


def test_invalid_ohlc_is_rejected():
    rows = [{"timestamp": "2026-01-01T00:00:00+00:00", "symbol": "AAA", "open": 105, "high": 100, "low": 99, "close": 100}]
    try:
        _run(rows, lambda row: {"action": "WAIT"})
    except ValueError as exc:
        assert "invalid candle OHLC" in str(exc)
    else:
        raise AssertionError("invalid OHLC candle was accepted")
