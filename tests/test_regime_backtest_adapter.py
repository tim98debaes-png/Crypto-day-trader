from backtest_engine import HistoricalBacktester
from regime_backtest_adapter import gate_signal, wrap_signal_provider


def context(**overrides):
    values = {
        "ema20_1h": 120.0,
        "ema50_1h": 110.0,
        "ema200_1h": 100.0,
        "adx1h": 25.0,
        "vol_regime_1h": 1.0,
        "btc_ema20_1h": 120.0,
        "btc_ema50_1h": 110.0,
        "btc_ema200_1h": 100.0,
        "btc_adx1h": 25.0,
        "btc_vol_regime_1h": 1.0,
    }
    values.update(overrides)
    return values


def test_allowed_long_is_preserved_and_enriched():
    result = gate_signal(
        {"action": "LONG", "stop_distance": 2.0, "rr": 2.0},
        context(),
    )
    assert result["action"] == "LONG"
    assert result["regime"] == "TREND_UP"
    assert result["btc_regime"] == "TREND_UP"


def test_long_is_blocked_when_asset_regime_is_down():
    result = gate_signal(
        {"action": "LONG", "stop_distance": 2.0, "rr": 2.0},
        context(ema20_1h=90.0, ema50_1h=100.0, ema200_1h=110.0),
    )
    assert result["action"] == "WAIT"
    assert result["reason"].startswith("regime_gate:TREND_DOWN")


def test_long_is_blocked_when_btc_regime_is_down():
    result = gate_signal(
        {"action": "LONG", "stop_distance": 2.0, "rr": 2.0},
        context(
            btc_ema20_1h=90.0,
            btc_ema50_1h=100.0,
            btc_ema200_1h=110.0,
        ),
    )
    assert result["action"] == "WAIT"
    assert "btc:TREND_DOWN" in result["reason"]


def test_missing_context_fails_closed():
    candle = context()
    candle.pop("btc_adx1h")
    result = gate_signal(
        {"action": "LONG", "stop_distance": 2.0, "rr": 2.0},
        candle,
    )
    assert result == {"action": "WAIT", "reason": "missing_regime_context"}


def test_gate_is_integrated_as_a_backtest_signal_provider():
    candles = []
    for index in range(4):
        row = {
            "timestamp": f"2026-01-01T00:0{index}:00",
            "symbol": "TEST",
            "close": 100.0,
            **context(),
        }
        candles.append(row)

    provider = wrap_signal_provider(
        lambda _row: {
            "action": "LONG",
            "stop_distance": 1.0,
            "rr": 2.0,
        }
    )
    result = HistoricalBacktester(
        capital=1000.0,
        risk_pct=0.5,
        fee_pct=0.0,
        slippage_pct=0.0,
    ).run(candles, provider)

    assert result.summary()["closed_trades"] == 1


def test_backtest_gate_blocks_entries_in_hostile_regime():
    candles = []
    for index in range(4):
        row = {
            "timestamp": f"2026-01-01T00:0{index}:00",
            "symbol": "TEST",
            "close": 100.0,
            **context(ema20_1h=90.0, ema50_1h=100.0, ema200_1h=110.0),
        }
        candles.append(row)

    provider = wrap_signal_provider(
        lambda _row: {
            "action": "LONG",
            "stop_distance": 1.0,
            "rr": 2.0,
        }
    )
    result = HistoricalBacktester(
        capital=1000.0,
        risk_pct=0.5,
        fee_pct=0.0,
        slippage_pct=0.0,
    ).run(candles, provider)

    assert result.summary()["closed_trades"] == 0
