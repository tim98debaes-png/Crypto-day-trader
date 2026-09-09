"""Apply the fixed market-regime/BTC filters to historical strategy signals.

This adapter deliberately sits between an existing signal provider and the
historical backtester. It does not change sizing, stops, exits, fees, slippage,
or optimizer parameters. A missing/invalid context fails closed when the gate
is enabled, preventing accidental bypasses in research runs.
"""

from __future__ import annotations

from typing import Callable, Optional

from regime_filter import build_market_context

SignalProvider = Callable[[dict], Optional[dict]]

_REQUIRED_CONTEXT = (
    "ema20_1h",
    "ema50_1h",
    "ema200_1h",
    "adx1h",
    "vol_regime_1h",
    "btc_ema20_1h",
    "btc_ema50_1h",
    "btc_ema200_1h",
    "btc_adx1h",
    "btc_vol_regime_1h",
)


def gate_signal(signal: Optional[dict], candle: dict) -> dict:
    """Gate one already-generated signal using closed HTF/BTC context."""
    base = dict(signal or {})
    action = str(base.get("action", "WAIT")).upper()

    if action not in {"LONG", "SHORT"}:
        return base

    missing = [name for name in _REQUIRED_CONTEXT if name not in candle]
    if missing:
        return {"action": "WAIT", "reason": "missing_regime_context"}

    context = build_market_context(
        ema20=float(candle["ema20_1h"]),
        ema50=float(candle["ema50_1h"]),
        ema200=float(candle["ema200_1h"]),
        adx=float(candle["adx1h"]),
        vol_regime=float(candle["vol_regime_1h"]),
        btc_ema20=float(candle["btc_ema20_1h"]),
        btc_ema50=float(candle["btc_ema50_1h"]),
        btc_ema200=float(candle["btc_ema200_1h"]),
        btc_adx=float(candle["btc_adx1h"]),
        btc_vol_regime=float(candle["btc_vol_regime_1h"]),
    )

    if action == "LONG":
        allowed = context.long_allowed and context.btc_long_allowed
    else:
        allowed = context.short_allowed and context.btc_short_allowed

    if allowed:
        enriched = dict(base)
        enriched["regime"] = context.regime
        enriched["btc_regime"] = context.btc_regime
        return enriched

    return {
        "action": "WAIT",
        "reason": (
            f"regime_gate:{context.regime}/"
            f"btc:{context.btc_regime}"
        ),
    }


def wrap_signal_provider(
    signal_provider: SignalProvider,
) -> SignalProvider:
    """Return a historical signal provider with the fixed entry gate applied."""
    def filtered(candle: dict) -> Optional[dict]:
        return gate_signal(signal_provider(candle), candle)

    return filtered
