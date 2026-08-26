import pytest

from multi_asset_scanner import AssetSnapshot, liquid_universe, rank_assets


def test_default_universe_has_50_unique_usdt_assets():
    universe = liquid_universe()
    assert len(universe) == 50
    assert len(set(universe)) == 50
    assert all(symbol.endswith("USDT") for symbol in universe)


def test_universe_normalizes_deduplicates_and_caps():
    universe = liquid_universe(["btcusdt", "BTCUSDT", "ethusdt", "bad"], max_assets=2)
    assert universe == ("BTCUSDT", "ETHUSDT")


def test_universe_rejects_invalid_cap():
    with pytest.raises(ValueError):
        liquid_universe(max_assets=0)


def test_rank_assets_filters_illiquid_and_returns_top_candidates():
    snapshots = [
        AssetSnapshot("BTCUSDT", 100, 100_000_000, change_pct=2.0, volatility_pct=3.0),
        AssetSnapshot("ETHUSDT", 100, 50_000_000, change_pct=4.0, volatility_pct=5.0),
        AssetSnapshot("LOWUSDT", 100, 1_000_000, change_pct=20.0, volatility_pct=20.0),
    ]
    ranked = rank_assets(snapshots, min_quote_volume=5_000_000, max_candidates=2)
    assert [item.symbol for item in ranked] == ["BTCUSDT", "ETHUSDT"]
    assert all(item.score > 0 for item in ranked)


def test_rank_assets_rejects_invalid_parameters():
    with pytest.raises(ValueError):
        rank_assets([], min_quote_volume=-1)
    with pytest.raises(ValueError):
        rank_assets([], max_candidates=0)
