"""Strategy V3: adaptive, regime-aware crypto day-trading research engine.

The V3 design separates market regime, setup quality, relative strength,
risk sizing, trade management and portfolio admission. It is intentionally
pure/deterministic so the same decision can be replayed in backtests, paper
trading and live execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite, sqrt
from statistics import mean
from typing import Mapping, Sequence


REGIMES = ("TREND_UP", "TREND_DOWN", "RANGE", "HIGH_VOL", "LOW_VOL", "TRANSITION")
DIRECTIONS = ("LONG", "SHORT")


@dataclass(frozen=True)
class V3Config:
    min_setup_score: float = 0.62
    strong_setup_score: float = 0.78
    max_risk_pct: float = 0.75
    base_risk_pct: float = 0.50
    min_risk_pct: float = 0.15
    max_total_open_risk_pct: float = 3.0
    max_open_positions: int = 4
    max_positions_per_sector: int = 2
    max_correlation: float = 0.75
    correlation_window: int = 12
    stop_atr_multiple: float = 1.5
    max_stop_pct: float = 0.025
    partial_at_r: float = 1.0
    partial_fraction: float = 0.50
    trail_atr_multiple: float = 2.2
    time_stop_minutes: int = 360
    cooldown_after_loss_minutes: int = 30


@dataclass(frozen=True)
class Regime:
    name: str
    confidence: float
    volatility_pct: float
    trend_strength: float


@dataclass(frozen=True)
class Setup:
    direction: str
    score: float
    regime: str
    reasons: tuple[str, ...]
    features: Mapping[str, float | bool | str]


@dataclass(frozen=True)
class TradePlan:
    direction: str
    entry_price: float
    stop_price: float
    stop_distance: float
    risk_pct: float
    position_notional: float
    partial_price: float
    trail_atr_multiple: float
    time_stop_minutes: int
    setup_score: float
    regime: str


def _f(value: object) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if isfinite(x) else None


def _close(c: Mapping[str, object]) -> float | None:
    return _f(c.get("close"))


def _closes(candles: Sequence[Mapping[str, object]]) -> list[float]:
    out: list[float] = []
    for c in candles:
        v = _close(c)
        if v is None or v <= 0:
            return []
        out.append(v)
    return out


def _returns(prices: Sequence[float]) -> list[float]:
    return [b / a - 1.0 for a, b in zip(prices, prices[1:]) if a > 0]


def _ema(values: Sequence[float], period: int) -> float | None:
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    value = values[0]
    for item in values[1:]:
        value = alpha * item + (1.0 - alpha) * value
    return value


def _atr(candles: Sequence[Mapping[str, object]], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    previous = _close(candles[-period - 1])
    if previous is None:
        return None
    trs: list[float] = []
    for c in candles[-period:]:
        h, l, cl = _f(c.get("high")), _f(c.get("low")), _close(c)
        if h is None or l is None or cl is None or h < l:
            return None
        trs.append(max(h - l, abs(h - previous), abs(l - previous)))
        previous = cl
    return mean(trs)


def _slope(values: Sequence[float], lookback: int) -> float | None:
    if len(values) <= lookback or values[-1 - lookback] <= 0:
        return None
    return values[-1] / values[-1 - lookback] - 1.0


def _std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def relative_strength(asset: Sequence[Mapping[str, object]], benchmark: Sequence[Mapping[str, object]] | None, lookback: int = 12) -> float:
    """Return asset return minus benchmark return over the same horizon."""
    a = _closes(asset)
    if not a or benchmark is None:
        return 0.0
    b = _closes(benchmark)
    if not b:
        return 0.0
    n = min(lookback, len(a) - 1, len(b) - 1)
    if n <= 0:
        return 0.0
    return (a[-1] / a[-1 - n] - 1.0) - (b[-1] / b[-1 - n] - 1.0)


def classify_regime(candles_1h: Sequence[Mapping[str, object]], config: V3Config = V3Config()) -> Regime:
    prices = _closes(candles_1h)
    if len(prices) < 55:
        return Regime("TRANSITION", 0.0, 0.0, 0.0)
    fast, slow = _ema(prices, 20), _ema(prices, 50)
    slope = _slope(prices, 8)
    returns = _returns(prices[-25:])
    vol = _std(returns) * sqrt(24.0) * 100.0
    if fast is None or slow is None or slope is None:
        return Regime("TRANSITION", 0.0, vol, 0.0)
    separation = abs(fast / slow - 1.0)
    trend_strength = min(1.0, separation / 0.02 + abs(slope) / 0.04)
    if vol >= 4.0:
        return Regime("HIGH_VOL", min(1.0, vol / 8.0), vol, trend_strength)
    if vol <= 0.75:
        return Regime("LOW_VOL", min(1.0, (0.75 - vol) / 0.75 + 0.25), vol, trend_strength)
    if fast > slow and slope > 0.002:
        return Regime("TREND_UP", min(1.0, 0.5 + trend_strength / 2), vol, trend_strength)
    if fast < slow and slope < -0.002:
        return Regime("TREND_DOWN", min(1.0, 0.5 + trend_strength / 2), vol, trend_strength)
    return Regime("RANGE", max(0.5, 1.0 - trend_strength), vol, trend_strength)


def _volume_ratio(candles: Sequence[Mapping[str, object]], lookback: int = 20) -> float:
    if len(candles) < lookback + 1:
        return 1.0
    current = _f(candles[-1].get("volume"))
    history = [_f(c.get("volume")) for c in candles[-lookback - 1:-1]]
    if current is None or any(v is None for v in history):
        return 1.0
    avg = mean(v for v in history if v is not None)
    return current / avg if avg > 0 else 1.0


def _bounce_quality(candles: Sequence[Mapping[str, object]], direction: str, atr: float) -> float:
    if len(candles) < 4 or atr <= 0:
        return 0.0
    c = candles[-1]
    o, h, l, cl = map(_f, (c.get("open"), c.get("high"), c.get("low"), c.get("close")))
    if None in (o, h, l, cl):
        return 0.0
    body = abs(cl - o) / atr
    rng = max(h - l, 1e-12)
    close_location = (cl - l) / rng
    if direction == "LONG":
        return min(1.0, max(0.0, body / 0.5) * 0.5 + close_location * 0.5) if cl > o else 0.0
    return min(1.0, max(0.0, body / 0.5) * 0.5 + (1.0 - close_location) * 0.5) if cl < o else 0.0


def score_setup(
    candles_5m: Sequence[Mapping[str, object]],
    candles_15m: Sequence[Mapping[str, object]],
    candles_1h: Sequence[Mapping[str, object]],
    direction: str,
    btc_1h: Sequence[Mapping[str, object]] | None = None,
    config: V3Config = V3Config(),
) -> Setup | None:
    if direction not in DIRECTIONS or min(len(candles_5m), len(candles_15m), len(candles_1h)) < 55:
        return None
    p5, p15, p1 = _closes(candles_5m), _closes(candles_15m), _closes(candles_1h)
    atr = _atr(candles_5m)
    if not p5 or not p15 or not p1 or atr is None or atr <= 0:
        return None
    regime = classify_regime(candles_1h, config)
    e15f, e15s = _ema(p15, 20), _ema(p15, 50)
    slope15 = _slope(p15, 4)
    rs = relative_strength(candles_1h, btc_1h)
    vr = _volume_ratio(candles_5m)
    bounce = _bounce_quality(candles_5m, direction, atr)
    price = p5[-1]
    distance_fast = abs(price - (_ema(p5, 20) or price)) / atr
    trend = 1.0 if ((direction == "LONG" and regime.name == "TREND_UP") or (direction == "SHORT" and regime.name == "TREND_DOWN")) else 0.0
    trend *= regime.confidence
    momentum = min(1.0, abs(slope15 or 0.0) / 0.01)
    momentum = momentum if ((direction == "LONG" and (slope15 or 0) > 0) or (direction == "SHORT" and (slope15 or 0) < 0)) else 0.0
    rel = min(1.0, max(0.0, (rs if direction == "LONG" else -rs) / 0.03 + 0.5))
    participation = min(1.0, vr / 1.5)
    location = max(0.0, 1.0 - distance_fast / 2.0)
    regime_fit = 1.0 if regime.name not in ("HIGH_VOL", "LOW_VOL") else 0.65
    components = {"trend": trend, "momentum": momentum, "relative_strength": rel, "participation": participation, "bounce": bounce, "location": location, "regime_fit": regime_fit}
    weights = {"trend": .22, "momentum": .16, "relative_strength": .16, "participation": .10, "bounce": .16, "location": .10, "regime_fit": .10}
    score = sum(components[k] * weights[k] for k in components)
    reasons = tuple(k for k, v in components.items() if v >= 0.60)
    features = {**components, "regime": regime.name, "regime_confidence": regime.confidence, "volatility_pct": regime.volatility_pct, "trend_strength": regime.trend_strength, "relative_strength": rs, "relative_volume": vr, "atr": atr, "ema20_15m": e15f or 0.0, "ema50_15m": e15s or 0.0}
    return Setup(direction, score, regime.name, reasons, features)


def select_setup(*setups: Setup | None) -> Setup | None:
    valid = [s for s in setups if s is not None]
    return max(valid, key=lambda s: (s.score, len(s.reasons))) if valid else None


def position_risk_pct(setup: Setup, config: V3Config = V3Config()) -> float:
    """Scale risk continuously with setup quality and reduce risk in unstable regimes."""
    quality = (setup.score - config.min_setup_score) / max(1e-9, 1.0 - config.min_setup_score)
    risk = config.min_risk_pct + max(0.0, min(1.0, quality)) * (config.max_risk_pct - config.min_risk_pct)
    if setup.regime in ("HIGH_VOL", "TRANSITION"):
        risk *= 0.60
    elif setup.regime == "LOW_VOL":
        risk *= 0.85
    return min(config.max_risk_pct, max(config.min_risk_pct, risk))


def build_trade_plan(setup: Setup, equity: float, entry_price: float, atr: float, config: V3Config = V3Config()) -> TradePlan | None:
    if equity <= 0 or entry_price <= 0 or atr <= 0 or setup.score < config.min_setup_score:
        return None
    distance = min(atr * config.stop_atr_multiple, entry_price * config.max_stop_pct)
    if distance <= 0:
        return None
    stop = entry_price - distance if setup.direction == "LONG" else entry_price + distance
    risk_pct = position_risk_pct(setup, config)
    risk_cash = equity * risk_pct / 100.0
    notional = risk_cash / (distance / entry_price)
    partial = entry_price + distance if setup.direction == "LONG" else entry_price - distance
    return TradePlan(setup.direction, entry_price, stop, distance, risk_pct, notional, partial, config.trail_atr_multiple, config.time_stop_minutes, setup.score, setup.regime)


def should_exit(
    direction: str,
    entry_price: float,
    current_price: float,
    stop_price: float,
    atr: float,
    bars_open: int,
    setup_score: float,
    config: V3Config = V3Config(),
) -> tuple[bool, str]:
    if direction == "LONG" and current_price <= stop_price:
        return True, "STOP"
    if direction == "SHORT" and current_price >= stop_price:
        return True, "STOP"
    risk = abs(entry_price - stop_price)
    if risk <= 0:
        return False, "HOLD"
    r = (current_price - entry_price) / risk if direction == "LONG" else (entry_price - current_price) / risk
    if r >= config.partial_at_r and setup_score < config.strong_setup_score:
        return True, "PARTIAL_OR_REASSESS"
    if bars_open >= config.time_stop_minutes / 5 and r < 0.25:
        return True, "TIME_STOP"
    return False, "HOLD"
