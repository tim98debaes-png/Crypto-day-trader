from paper_engine import PaperAccount
from paper_router import candidate_is_approved, route_candidate


def good_candidate():
    return {
        "Status": "ROBUST",
        "Stability": 75,
        "OOS PF": 1.5,
        "OOS %": 12,
        "OOS trades": 20,
        "OOS DD": -8,
        "MC P05 %": -2,
    }


def test_candidate_gate_accepts_production_optimizer_candidate():
    assert candidate_is_approved(good_candidate(), mode="production") is True


def test_candidate_gate_blocks_weak_stability_in_production():
    candidate = good_candidate()
    candidate["Stability"] = 59
    assert candidate_is_approved(candidate, mode="production") is False


def test_router_opens_only_approved_candidate():
    account = PaperAccount(capital=1000, fee_pct=0, slippage_pct=0)
    result = route_candidate(
        account,
        good_candidate(),
        {"symbol": "BTCUSDT", "direction": "LONG", "price": 100, "stop_distance": 2, "rr": 2},
    )
    assert result["action"] == "OPEN"
    assert account.position is not None


def test_router_blocks_watch_candidate():
    account = PaperAccount(capital=1000)
    candidate = good_candidate()
    candidate["Status"] = "WATCH"
    result = route_candidate(
        account,
        candidate,
        {"symbol": "BTCUSDT", "direction": "LONG", "price": 100, "stop_distance": 2, "rr": 2},
    )
    assert result["action"] == "BLOCK"
    assert account.position is None
