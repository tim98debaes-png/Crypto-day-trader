from multi_asset_live_paper_session import run_multi_asset_paper_session


def test_direction_aware_selection_prefers_both_sides_when_available():
    # Regression fixture: four valid LONGs must not consume all four slots when
    # valid SHORTs are available at the same time.
    candidates = [
        {"symbol": "L1USDT", "price": 100.0, "direction": "LONG", "tier": "A", "score": 5, "candidate_score": 90.0, "volatility_pct": 0.20},
        {"symbol": "L2USDT", "price": 100.0, "direction": "LONG", "tier": "A", "score": 5, "candidate_score": 89.0, "volatility_pct": 0.20},
        {"symbol": "L3USDT", "price": 100.0, "direction": "LONG", "tier": "A", "score": 5, "candidate_score": 88.0, "volatility_pct": 0.20},
        {"symbol": "L4USDT", "price": 100.0, "direction": "LONG", "tier": "A", "score": 5, "candidate_score": 87.0, "volatility_pct": 0.20},
        {"symbol": "S1USDT", "price": 100.0, "direction": "SHORT", "tier": "A", "score": 5, "candidate_score": 86.0, "volatility_pct": 0.20},
        {"symbol": "S2USDT", "price": 100.0, "direction": "SHORT", "tier": "A", "score": 5, "candidate_score": 85.0, "volatility_pct": 0.20},
    ]
    selected = []
    remaining = sorted(candidates, key=lambda x: (-x["score"], -x["candidate_score"], x["symbol"]))
    while remaining and len(selected) < 4:
        directions = {item["direction"] for item in selected}
        preferred = "SHORT" if "LONG" in directions else ("LONG" if "SHORT" in directions else None)
        pool = [item for item in remaining if item["direction"] == preferred] if preferred else []
        chosen = pool[0] if pool else remaining[0]
        selected.append(chosen)
        remaining.remove(chosen)
    assert [item["direction"] for item in selected] == ["LONG", "SHORT", "LONG", "SHORT"]
