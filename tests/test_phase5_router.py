from paper_engine import PaperAccount
from paper_router import candidate_is_approved, route_candidate


def good_candidate():
    return {
        "Status": "TRADE",
        "MC Robustness": 75,
        "MC Profit Probability": 62,
        "OOS Return": 12,
    }


def test_candidate_gate_accepts_robust_oos_candidate():
    assert candidate_is_approved(good_candidate()) is True


def test_candidate_gate_blocks_weak_candidate():
    candidate = good_candidate()
    candidate["MC Robustness"] = 49
    assert candidate_is_approved(candidate) is False


def test_router_opens_only_approved_candidate():
    account = PaperAccount(capital=1000, fee_pct=0, slippage_pct=0)
    result = route_candidate(
        account,
        good_candidate(),
        {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "price": 100,
            "stop_distance": 2,
            "rr": 2,
        },
    )
    assert result["action"] == "OPEN"
    assert account.position is not None


def test_router_blocks_without_creating_position():
    account = PaperAccount(capital=1000)
    candidate = good_candidate()
    candidate["Status"] = "WATCH"
    result = route_candidate(
        account,
        candidate,
        {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "price": 100,
            "stop_distance": 2,
            "rr": 2,
        },
    )
    assert result["action"] == "BLOCK"
    assert account.position is None
