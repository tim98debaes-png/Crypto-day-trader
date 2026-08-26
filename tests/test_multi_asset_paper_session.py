import pytest

from multi_asset_paper_session import scan_and_select, submit_paper_candidates
from multi_asset_scanner import AssetSnapshot


def test_scan_and_select_returns_top_candidates():
    snapshots = [
        AssetSnapshot("BTCUSDT", 100, 100_000_000, change_pct=1.0, volatility_pct=2.0),
        AssetSnapshot("ETHUSDT", 100, 80_000_000, change_pct=4.0, volatility_pct=4.0),
        AssetSnapshot("SOLUSDT", 100, 60_000_000, change_pct=3.0, volatility_pct=5.0),
    ]
    result = scan_and_select(snapshots, max_candidates=2)
    assert result.scanned == 3
    assert result.eligible == 3
    assert len(result.candidates) == 2


def test_submit_is_position_capped_and_paper_callback_only():
    snapshots = [
        AssetSnapshot("BTCUSDT", 100, 100_000_000, change_pct=1.0, volatility_pct=2.0),
        AssetSnapshot("ETHUSDT", 100, 80_000_000, change_pct=4.0, volatility_pct=4.0),
    ]
    result = scan_and_select(snapshots)
    submitted = []
    selected = submit_paper_candidates(result.candidates, submitted.append, max_positions=1)
    assert len(selected) == 1
    assert submitted == list(selected)


def test_submit_rejects_invalid_position_cap():
    with pytest.raises(ValueError):
        submit_paper_candidates([], lambda _: None, max_positions=0)
