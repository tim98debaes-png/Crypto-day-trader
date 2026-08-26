from market_feed import MarketSnapshot


def test_market_snapshot_is_normalized():
    snapshot = MarketSnapshot("btcusdt", 123.45)
    assert snapshot.symbol == "btcusdt"
    assert snapshot.price == 123.45


def test_feed_has_read_only_public_endpoint():
    from market_feed import BinancePublicFeed
    assert BinancePublicFeed.BASE_URL.endswith("/api/v3/ticker/24hr")
    assert "order" not in BinancePublicFeed.BASE_URL.lower()
