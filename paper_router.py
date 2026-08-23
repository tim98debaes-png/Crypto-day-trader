"""Gate validated optimizer candidates into the paper-trading engine."""

from paper_engine import PaperAccount


def candidate_is_approved(candidate: dict) -> bool:
    """Require the Phase 3/4 quality gates before paper execution."""
    status = str(candidate.get("Status", "")).upper()
    robustness = float(candidate.get("MC Robustness", 0.0) or 0.0)
    probability = float(candidate.get("MC Profit Probability", 0.0) or 0.0)
    oos_return = float(candidate.get("OOS Return", candidate.get("return", 0.0)) or 0.0)

    return (
        status == "TRADE"
        and robustness >= 60.0
        and probability >= 55.0
        and oos_return > 0.0
    )


def route_candidate(account: PaperAccount, candidate: dict, market: dict):
    """Open one paper position only when every quality gate passes."""
    if not candidate_is_approved(candidate):
        return {"action": "BLOCK", "reason": "quality_gates_failed"}

    return {
        "action": "OPEN",
        "position": account.open_position(
            symbol=str(market["symbol"]),
            direction=str(market["direction"]),
            price=float(market["price"]),
            stop_distance=float(market["stop_distance"]),
            rr=float(market["rr"]),
            timestamp=market.get("timestamp"),
        ),
    }
