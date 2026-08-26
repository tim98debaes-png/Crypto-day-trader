"""Phase 31 market-data resilience tests."""

import json

import pytest

import market_feed


def test_phase31_feed_rejects_non_numeric_price(monkeypatch):
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return json.dumps({"price": "not-a-number"}).encode()

    monkeypatch.setattr(market_feed, "urlopen", lambda *args, **kwargs: Response())
    with pytest.raises(ValueError):
        market_feed.BinancePublicFeed().snapshot("BTCUSDT")


def test_phase31_feed_rejects_non_positive_price(monkeypatch):
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return json.dumps({"price": "0"}).encode()

    monkeypatch.setattr(market_feed, "urlopen", lambda *args, **kwargs: Response())
    with pytest.raises(ValueError, match="positive"):
        market_feed.BinancePublicFeed().snapshot("BTCUSDT")


def test_phase31_feed_preserves_normalized_symbol(monkeypatch):
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return json.dumps({"price": "100.5"}).encode()

    monkeypatch.setattr(market_feed, "urlopen", lambda *args, **kwargs: Response())
    snapshot = market_feed.BinancePublicFeed().snapshot("btcusdt")
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.price == 100.5
