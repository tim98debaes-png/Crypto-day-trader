"""Portfolio-level admission controls for Strategy V3.

The engine prevents concentration before an order is created. It is deliberately
stateless: callers provide current open positions and recent return histories.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Mapping, Sequence

from strategy_risk_controls import sector_for


@dataclass(frozen=True)
class PortfolioSnapshot:
    equity: float
    open_symbols: tuple[str, ...]
    open_risk_pct: float
    recent_losses: int = 0


@dataclass(frozen=True)
class Admission:
    allowed: bool
    reason: str
    correlation: float | None = None


def _returns(prices: Sequence[float]) -> list[float]:
    return [b / a - 1.0 for a, b in zip(prices, prices[1:]) if a > 0]


def _corr(a: Sequence[float], b: Sequence[float]) -> float | None:
    n = min(len(a), len(b))
    if n < 3:
        return None
    x, y = list(a[-n:]), list(b[-n:])
    mx, my = sum(x) / n, sum(y) / n
    dx, dy = [v - mx for v in x], [v - my for v in y]
    den = sqrt(sum(v*v for v in dx) * sum(v*v for v in dy))
    return sum(u*v for u, v in zip(dx, dy)) / den if den else None


def admit(
    symbol: str,
    proposed_risk_pct: float,
    snapshot: PortfolioSnapshot,
    histories: Mapping[str, Sequence[float]],
    *,
    max_positions: int = 4,
    max_total_risk_pct: float = 3.0,
    max_sector_positions: int = 2,
    max_correlation: float = 0.75,
    correlation_window: int = 12,
) -> Admission:
    symbol = symbol.upper()
    if proposed_risk_pct <= 0:
        return Admission(False, "INVALID_RISK")
    if len(snapshot.open_symbols) >= max_positions:
        return Admission(False, "MAX_POSITIONS")
    if snapshot.open_risk_pct + proposed_risk_pct > max_total_risk_pct + 1e-12:
        return Admission(False, "MAX_TOTAL_RISK")
    sector = sector_for(symbol)
    sector_count = sum(sector_for(s) == sector for s in snapshot.open_symbols)
    if sector_count >= max_sector_positions:
        return Admission(False, "MAX_SECTOR_EXPOSURE")
    candidate = _returns(histories.get(symbol, ()))
    best: float | None = None
    for other in snapshot.open_symbols:
        corr = _corr(candidate, _returns(histories.get(other, ())))
        if corr is not None:
            best = corr if best is None else max(best, corr)
            if corr >= max_correlation:
                return Admission(False, "CORRELATED_EXPOSURE", corr)
    return Admission(True, "ADMITTED", best)
