from strategy_v2 import _short_edge_trigger


def test_short_edge_requires_price_near_fast_and_bearish_bounce():
    candles = [
        {"open": 100.0, "high": 101.2, "low": 99.8, "close": 100.5, "volume": 100.0},
        {"open": 100.4, "high": 101.0, "low": 99.7, "close": 99.9, "volume": 120.0},
    ]
    ok, depth = _short_edge_trigger(candles, atr=2.0, ema_fast=100.0)
    assert ok is True
    assert depth >= 0


def test_short_edge_rejects_price_too_far_from_fast():
    candles = [
        {"open": 100.0, "high": 101.0, "low": 99.8, "close": 101.0, "volume": 100.0},
        {"open": 101.0, "high": 101.5, "low": 100.5, "close": 101.0, "volume": 120.0},
    ]
    ok, _ = _short_edge_trigger(candles, atr=1.0, ema_fast=100.0)
    assert ok is False


def test_short_edge_rejects_non_bearish_rejection():
    candles = [
        {"open": 100.0, "high": 101.2, "low": 99.8, "close": 100.5, "volume": 100.0},
        {"open": 100.4, "high": 101.0, "low": 99.7, "close": 100.6, "volume": 120.0},
    ]
    ok, _ = _short_edge_trigger(candles, atr=2.0, ema_fast=100.0)
    assert ok is False
