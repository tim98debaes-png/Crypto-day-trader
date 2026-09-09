"""Deterministic market-regime and BTC-context filters.

The filters are deliberately fixed rather than optimizer-tuned. They are
intended to reduce exposure to structurally hostile market conditions without
adding another parameter-search dimension.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketContext:
    """Closed-candle market context used by the entry gate."""

    regime: str
    long_allowed: bool
    short_allowed: bool
    btc_regime: str
    btc_long_allowed: bool
    btc_short_allowed: bool


def classify_regime(
    ema20: float,
    ema50: float,
    ema200: float,
    adx: float,
    vol_regime: float,
) -> str:
    """Classify a closed higher-timeframe candle.

    TREND_* requires ordered EMAs and ADX >= 18. HIGH_VOL is a hard risk-off
    regime when volatility is more than 3x its rolling baseline. Everything
    else is RANGE.
    """
    values = (ema20, ema50, ema200, adx, vol_regime)
    if not all(_is_finite(value) for value in values):
        return "UNKNOWN"

    if vol_regime > 3.0:
        return "HIGH_VOL"

    if adx >= 18 and ema20 > ema50 > ema200:
        return "TREND_UP"

    if adx >= 18 and ema20 < ema50 < ema200:
        return "TREND_DOWN"

    return "RANGE"


def btc_direction_allowed(
    direction: str,
    btc_regime: str,
) -> bool:
    """Allow a trade unless BTC is structurally opposed to its direction."""
    if direction == "LONG":
        return btc_regime not in {"TREND_DOWN", "HIGH_VOL", "UNKNOWN"}
    if direction == "SHORT":
        return btc_regime not in {"TREND_UP", "HIGH_VOL", "UNKNOWN"}
    return False


def market_direction_allowed(
    direction: str,
    regime: str,
) -> bool:
    """Gate entries by the asset's own higher-timeframe market regime."""
    if direction == "LONG":
        return regime in {"TREND_UP"}
    if direction == "SHORT":
        return regime in {"TREND_DOWN"}
    return False


def build_market_context(
    *,
    ema20: float,
    ema50: float,
    ema200: float,
    adx: float,
    vol_regime: float,
    btc_ema20: float,
    btc_ema50: float,
    btc_ema200: float,
    btc_adx: float,
    btc_vol_regime: float,
) -> MarketContext:
    regime = classify_regime(
        ema20,
        ema50,
        ema200,
        adx,
        vol_regime,
    )
    btc_regime = classify_regime(
        btc_ema20,
        btc_ema50,
        btc_ema200,
        btc_adx,
        btc_vol_regime,
    )

    return MarketContext(
        regime=regime,
        long_allowed=market_direction_allowed("LONG", regime),
        short_allowed=market_direction_allowed("SHORT", regime),
        btc_regime=btc_regime,
        btc_long_allowed=btc_direction_allowed("LONG", btc_regime),
        btc_short_allowed=btc_direction_allowed("SHORT", btc_regime),
    )


def _is_finite(value: float) -> bool:
    try:
        return value == value and abs(float(value)) != float("inf")
    except (TypeError, ValueError):
        return False
