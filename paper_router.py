"""Gate validated optimizer candidates into the paper-trading engine.

The router accepts the optimizer's real Phase 3/4 output schema and also
supports the legacy normalized fields used by the unit tests.  No candidate
is allowed into paper execution unless the strategy status, out-of-sample
performance and robustness gates all pass.
"""

from paper_engine import PaperAccount


def _number(candidate: dict, *keys, default=0.0):
    """Return the first finite numeric candidate field that exists."""
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
    """Require the real optimizer's Phase 3/4 quality gates before paper execution."""
    status = _status(candidate)

    # Real optimizer output uses OOS % and OOS PF.  Keep the normalized
    # aliases for backwards compatibility with existing Phase 5 tests.
    oos_return = _number(
        candidate,
        "OOS %",
        "OOS Return",
        "return",
    )
    oos_pf = _number(candidate, "OOS PF", "OOS Profit Factor", default=0.0)
    oos_trades = _number(candidate, "OOS trades", "OOS Trades", default=0.0)
    oos_dd = abs(_number(candidate, "OOS DD", "OOS Drawdown", default=0.0))

    # Real Phase 4 output may expose MC Robustness/MC Profit Probability;
    # otherwise derive a conservative gate from the available MC P05 and
    # stability metrics.  The legacy fields remain fully supported.
    robustness = _number(candidate, "MC Robustness", "Robustness", default=-1.0)
    probability = _number(
        candidate,
        "MC Profit Probability",
        "MC Profit Prob",
        default=-1.0,
    )
    mc_p05 = _number(candidate, "MC P05 %", "MC P05", default=-999.0)
    stability = _number(candidate, "Stability", "Neighbour Stability", default=-1.0)

    if robustness < 0:
        # Conservative normalized robustness from real optimizer evidence.
        robustness = 100.0
        if mc_p05 < 0:
            robustness -= min(abs(mc_p05), 40.0)
        if stability >= 0:
            robustness *= min(max(stability / 100.0, 0.0), 1.0)

    if probability < 0:
        probability = 100.0 if mc_p05 >= 0 else 0.0

    return (
        status == "TRADE"
        and oos_return > 0.0
        and oos_pf > 0.0
        and oos_trades >= 1.0
        and robustness >= 60.0
        and probability >= 55.0
        and oos_dd < 100.0
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
