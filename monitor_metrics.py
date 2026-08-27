from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping


@dataclass(frozen=True)
class MonitorDecision:
    status: str
    reason: str
    metrics_valid: bool
    statistically_ready: bool
    warnings: tuple[str, ...] = ()


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def evaluate_metrics(summary: Mapping[str, Any], *, min_trades: int = 30) -> MonitorDecision:
    """Validate paper metrics without treating a small sample as broken metrics.

    The previous monitor conflated 'not enough evidence' with 'invalid metrics'.
    This keeps hard data-quality failures BLOCKED, while correctly classifying
    small but internally consistent samples as INSUFFICIENT_DATA.
    """
    warnings: list[str] = []
    trades_raw = summary.get("closed_trades", summary.get("trades", 0))
    try:
        trades = int(trades_raw)
    except (TypeError, ValueError):
        return MonitorDecision("BLOCKED", "invalid_metrics: closed_trades is not an integer", False, False)

    if trades < 0:
        return MonitorDecision("BLOCKED", "invalid_metrics: negative trade count", False, False)

    for key in ("ending_equity", "return_pct", "max_drawdown_pct"):
        if _num(summary.get(key)) is None:
            return MonitorDecision("BLOCKED", f"invalid_metrics: missing/non-finite {key}", False, False)

    wins = summary.get("winning_trades")
    losses = summary.get("losing_trades")
    if wins is not None and losses is not None:
        try:
            wins, losses = int(wins), int(losses)
        except (TypeError, ValueError):
            return MonitorDecision("BLOCKED", "invalid_metrics: win/loss counts are invalid", False, False)
        if wins < 0 or losses < 0 or wins + losses != trades:
            return MonitorDecision("BLOCKED", "invalid_metrics: win/loss counts do not reconcile", False, False)

    pf = summary.get("profit_factor")
    if isinstance(pf, str) and pf.lower() in {"inf", "infinity"}:
        # Infinite PF is mathematically possible when losses are zero, but it is
        # not evidence of infinite edge. Keep it as a warning, not a parse error.
        warnings.append("profit_factor_infinite_zero_losses")
    elif pf is not None and _num(pf) is None:
        return MonitorDecision("BLOCKED", "invalid_metrics: non-finite profit_factor", False, False)

    if trades < min_trades:
        warnings.append(f"sample_below_minimum:{trades}<{min_trades}")
        return MonitorDecision("INSUFFICIENT_DATA", "insufficient_data: collect more closed trades", True, False, tuple(warnings))

    return MonitorDecision("READY", "metrics_valid_and_statistically_ready", True, True, tuple(warnings))
