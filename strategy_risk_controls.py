"""Research-stage portfolio risk controls used by the paper strategy.

The controls are deliberately deterministic and fail closed. They do not claim
a correlation estimate is predictive; they simply reduce concentration when
assets have recently moved together.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import sqrt
from typing import Mapping, Sequence

@dataclass(frozen=True)
class RiskConfig:
    standard_risk_pct: float = 0.50
    max_risk_pct_per_trade: float = 1.00
    max_total_open_risk_pct: float = 4.0
    max_open_positions: int = 4
    soft_open_positions: int = 3
    max_positions_per_sector: int = 2
    max_pairwise_correlation: float = 0.75
    correlation_window: int = 6
    trailing_atr_multiple: float = 2.2
    partial_take_profit_r: float = 1.0
    partial_take_profit_fraction: float = 0.50
    time_stop_minutes: int = 360
    volatility_floor_pct: float = 0.05
    volatility_ceiling_pct: float = 0.80
    # Run #72 showed ENA being re-entered LONG -> SHORT -> LONG inside one hour.
    # A short asset-specific cooldown reduces this churn without imposing a
    # global trading halt after one bad trade.
    loss_reentry_cooldown_minutes: int = 15
    win_reentry_cooldown_minutes: int = 5

    def __post_init__(self) -> None:
        if not 0 < self.standard_risk_pct <= self.max_risk_pct_per_trade:
            raise ValueError("invalid standard risk")
        if self.max_open_positions < 1 or self.soft_open_positions < 1:
            raise ValueError("position caps must be positive")
        if self.soft_open_positions > self.max_open_positions:
            raise ValueError("soft position cap cannot exceed hard cap")
        if self.max_positions_per_sector < 1:
            raise ValueError("sector cap must be positive")
        if not 0 < self.max_pairwise_correlation <= 1:
            raise ValueError("correlation threshold must be in (0,1]")
        if self.correlation_window < 3:
            raise ValueError("correlation window must be at least 3")
        if self.trailing_atr_multiple <= 0:
            raise ValueError("ATR multiple must be positive")
        if not 0 < self.partial_take_profit_fraction <= 1:
            raise ValueError("partial fraction must be in (0,1]")
        if self.time_stop_minutes < 1:
            raise ValueError("time stop must be positive")
        if self.volatility_floor_pct < 0 or self.volatility_ceiling_pct <= self.volatility_floor_pct:
            raise ValueError("invalid volatility range")
        if self.loss_reentry_cooldown_minutes < 0 or self.win_reentry_cooldown_minutes < 0:
            raise ValueError("re-entry cooldowns must be non-negative")

RISK_CONFIG = RiskConfig()

_SECTORS: dict[str, str] = {
    "BTCUSDT": "BTC", "ETHUSDT": "L1", "SOLUSDT": "L1", "ADAUSDT": "L1",
    "AVAXUSDT": "L1", "SUIUSDT": "L1", "TONUSDT": "L1", "DOTUSDT": "L1",
    "NEARUSDT": "L1", "APTUSDT": "L1", "ARBUSDT": "L2", "OPUSDT": "L2",
    "ATOMUSDT": "L1", "SEIUSDT": "L1", "TIAUSDT": "L1", "JUPUSDT": "DEFI",
    "UNIUSDT": "DEFI", "AAVEUSDT": "DEFI", "MKRUSDT": "DEFI", "RUNEUSDT": "DEFI",
    "BNBUSDT": "EXCHANGE", "XRPUSDT": "PAYMENTS", "TRXUSDT": "PAYMENTS",
    "XLMUSDT": "PAYMENTS", "LTCUSDT": "PAYMENTS", "BCHUSDT": "PAYMENTS",
    "DOGEUSDT": "MEME", "SHIBUSDT": "MEME", "PEPEUSDT": "MEME", "WIFUSDT": "MEME",
    "FLOKIUSDT": "MEME", "BONKUSDT": "MEME", "SANDUSDT": "GAMING", "MANAUSDT": "GAMING",
    "AXSUSDT": "GAMING", "EGLDUSDT": "L1", "INJUSDT": "DEFI", "HBARUSDT": "L1",
    "ALGOUSDT": "L1", "VETUSDT": "L1", "ICPUSDT": "L1", "QNTUSDT": "INFRA",
    "GRTUSDT": "INFRA", "FILUSDT": "INFRA", "ETCUSDT": "POW", "RENDERUSDT": "AI",
    "TAOUSDT": "AI", "ENAUSDT": "DEFI", "PYTHUSDT": "INFRA", "THETAUSDT": "AI",
}

def sector_for(symbol: str) -> str:
    return _SECTORS.get(str(symbol).upper(), "OTHER")

def pearson_correlation(a: Sequence[float], b: Sequence[float]) -> float | None:
    n = min(len(a), len(b))
    if n < 3:
        return None
    x = list(a[-n:]); y = list(b[-n:])
    mx = sum(x) / n; my = sum(y) / n
    dx = [v - mx for v in x]; dy = [v - my for v in y]
    denom = sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    if denom <= 0:
        return None
    return sum(u * v for u, v in zip(dx, dy)) / denom

def return_series(prices: Sequence[float]) -> list[float]:
    values = list(prices)
    result: list[float] = []
    for previous, current in zip(values, values[1:]):
        if previous > 0:
            result.append(current / previous - 1.0)
    return result

def exceeds_correlation_limit(symbol: str, open_symbols: Sequence[str], histories: Mapping[str, Sequence[float]], *, threshold: float = 0.75, window: int = 6) -> bool:
    candidate_returns = return_series(histories.get(symbol, ()))[-window:]
    for other in open_symbols:
        other_returns = return_series(histories.get(other, ()))[-window:]
        corr = pearson_correlation(candidate_returns, other_returns)
        if corr is not None and corr >= threshold:
            return True
    return False

def sector_position_count(symbol: str, open_symbols: Sequence[str]) -> int:
    sector = sector_for(symbol)
    return sum(1 for item in open_symbols if sector_for(item) == sector)
