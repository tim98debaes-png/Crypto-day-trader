"""Gate validated optimizer candidates into the paper-trading engine."""

from paper_engine import PaperAccount


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


def candidate_is_approved(candidate: dict) -> bool:
    """Match the paper gate to the optimizer's actual output contract.

    strategy_discovery returns TRADE, while optimize_coin normalizes a passing
    candidate to ROBUST.  Both are valid here.  The real optimizer exposes
    OOS PF, OOS %, OOS trades, OOS DD, Stability and MC P05 %; there is no
    genuine Monte-Carlo profit-probability field, so we must not fabricate one.
    """
    status = _status(candidate)
    if status not in {"TRADE", "ROBUST"}:
        return False

    oos_return = _number(candidate, "OOS %", "OOS Return", "return", default=-999.0)
    oos_pf = _number(candidate, "OOS PF", "OOS Profit Factor", "pf", default=0.0)
    oos_trades = _number(candidate, "OOS trades", "OOS Trades", "trades", default=0.0)
    oos_dd = _number(candidate, "OOS DD", "OOS Drawdown", "dd", default=-999.0)
    stability = _number(candidate, "Stability", "Neighbour Stability", default=-1.0)
    mc_p05 = _number(candidate, "MC P05 %", "MC P05", default=-999.0)

    # Exact Phase 3/4 production thresholds from candidate_status().
    return (
        oos_return > 0.0
        and oos_pf >= 1.20
        and oos_trades >= 15.0
        and oos_dd > -20.0
        and stability >= 60.0
        and mc_p05 > -10.0
    )


def route_candidate(account: PaperAccount, candidate: dict, market: dict):
    """Open one paper position only when every production gate passes."""
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
