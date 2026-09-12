import pytest

from strategy_v2 import _pullback_trigger


def _c(open_, high, low, close):
    return {"open": open_, "high": high, "low": low, "close": close, "volume": 100.0}


def test_long_requires_immediate_reclaim_before_current_impulse():
    candles = [
        _c(99.5, 100.0, 99.2, 99.0),
        _c(100.5, 101.0, 99.8, 101.0),
        _c(101.0, 102.0, 100.5, 102.0),
        _c(102.0, 103.0, 101.5, 103.0),
        _c(103.0, 104.5, 102.5, 104.5),
    ]
    ok, depth = _pullback_trigger(candles, "LONG", atr=1.0, ema_fast=100.0)
    assert ok is False
    assert depth == pytest.approx(0.8)


def test_short_requires_immediate_reclaim_before_current_impulse():
    candles = [
        _c(100.5, 100.8, 100.0, 101.0),
        _c(99.5, 100.2, 99.0, 99.0),
        _c(99.0, 99.5, 98.0, 98.0),
        _c(98.0, 98.5, 97.0, 97.0),
        _c(97.0, 97.5, 95.5, 95.5),
    ]
    ok, depth = _pullback_trigger(candles, "SHORT", atr=1.0, ema_fast=100.0)
    assert ok is False
    assert depth == pytest.approx(0.8)


def test_immediate_reclaim_with_impulse_is_accepted():
    candles = [
        _c(99.8, 100.8, 99.2, 99.0),
        _c(99.0, 100.2, 98.5, 99.0),
        _c(99.0, 100.0, 98.8, 99.2),
        _c(99.2, 100.1, 98.9, 99.0),
        _c(99.0, 101.5, 98.9, 101.5),
    ]
    ok, _ = _pullback_trigger(candles, "LONG", atr=1.0, ema_fast=100.0)
    assert ok is True
