"""Gate validated optimizer candidates into the paper-trading engine."""

from paper_engine import PaperAccount


# Research/paper mode deliberately uses softer validation than the eventual
# production gate. The production values remain unchanged so experimentation
# can increase candidate breadth without weakening the final safety bar.
RESEARCH_GATES = {
    "min_oos_return": 0.0,
    "min_oos_pf": 1.05,
    "min_oos_trades": 5.0,
    "max_oos_dd": -25.0,
    "min_stability": 50.0,
    "min_mc_p05": -15.0,
}

PRODUCTION_GATES = {
    "min_oos_return": 0.0,
    "min_oos_pf": 1.20,
    "min_oos_trades": 15.0,
    "max_oos_dd": -20.0,
    "min_stability": 60.0,
    "min_mc_p05": -10.0,
}


def _number(candidate: dict, *keys, default=0.0):
    for key in keys:
        value = candidate.get(key)
        if value is None or value == "":
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number == number and abs(number) != float("inf"):
            return number
    return float(default)


def _status(candidate: dict) -> str:
    return str(candidate.get("Status", candidate.get("status", ""))).upper().strip()


def candidate_is_approved(candidate: dict, *, mode: str = "research") -> bool:
    """Validate a candidate using research/paper or production thresholds."""
    status = _status(candidate)
    if status not in {"TRADE", "ROBUST"}:
        return False

    gates = PRODUCTION_GATES if str(mode).lower().strip() == "production" else RESEARCH_GATES
    oos_return = _number(candidate, "OOS %", "OOS Return", "return", default=-999.0)
    oos_pf = _number(candidate, "OOS PF", "OOS Profit Factor", "pf", default=0.0)
    oos_trades = _number(candidate, "OOS trades", "OOS Trades", "trades", default=0.0)
    oos_dd = _number(candidate, "OOS DD", "OOS Drawdown", "dd", default=-999.0)
    stability = _number(candidate, "Stability", "Neighbour Stability", default=-1.0)
    mc_p05 = _number(candidate, "MC P05 %", "MC P05", default=-999.0)

    return (
        oos_return > gates["min_oos_return"]
        and oos_pf >= gates["min_oos_pf"]
        and oos_trades >= gates["min_oos_trades"]
        and oos_dd > gates["max_oos_dd"]
        and stability >= gates["min_stability"]
        and mc_p05 > gates["min_mc_p05"]
    )


def route_candidate(account: PaperAccount, candidate: dict, market: dict, *, mode: str = "research"):
    """Open one paper position only when the selected validation gate passes."""
    if not candidate_is_approved(candidate, mode=mode):
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
