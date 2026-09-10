from strategy_v2 import generate_signal


def _series(n=80, trend=0.001, volume=100.0):
    rows = []
    price = 100.0
    for i in range(n):
        price *= 1.0 + trend
        rows.append({
            "open": price * (1.0 - trend * 0.2),
            "high": price * (1.0 + abs(trend) * 0.8),
            "low": price * (1.0 - abs(trend) * 0.8),
            "close": price,
            "volume": volume,
        })
    return rows


def test_v2_fails_closed_on_missing_history():
    assert generate_signal(_series(20), _series(20), _series(20)) is None


def test_v2_fails_closed_on_invalid_candle():
    candles = _series()
    candles[-1]["close"] = float("nan")
    assert generate_signal(candles, _series(), _series()) is None


def test_v2_does_not_trade_flat_market():
    flat = _series(trend=0.0)
    assert generate_signal(flat, flat, flat) is None


def test_v2_btc_filter_blocks_long_against_downtrend():
    asset = _series(trend=0.001)
    btc_down = _series(trend=-0.001)
    assert generate_signal(asset, asset, asset, btc_down) is None


def test_v2_btc_filter_blocks_short_against_uptrend():
    asset = _series(trend=-0.001)
    btc_up = _series(trend=0.001)
    assert generate_signal(asset, asset, asset, btc_up) is None
