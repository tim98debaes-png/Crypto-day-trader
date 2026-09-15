"""Evidence-based trend breakout strategy.

Design: volatility-normalized Donchian breakout + EMA regime + volume confirmation.
This is deliberately low-frequency and cost-aware; it is a research baseline,
not a claim of guaranteed profitability.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

import pandas as pd

Direction = Literal["LONG", "SHORT", "FLAT"]

@dataclass(frozen=True)
class TrendBreakoutConfig:
    fast_ema: int = 20
    slow_ema: int = 50
    breakout_window: int = 20
    atr_window: int = 14
    volume_window: int = 20
    min_volume_ratio: float = 1.0
    min_atr_pct: float = 0.20
    max_atr_pct: float = 8.0
    stop_atr: float = 2.0
    target_r: float = 2.5

@dataclass(frozen=True)
class Signal:
    direction: Direction
    entry: float
    stop_distance: float
    target_distance: float
    reason: str


def indicators(df: pd.DataFrame, cfg: TrendBreakoutConfig = TrendBreakoutConfig()) -> pd.DataFrame:
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    out = df.copy()
    out["ema_fast"] = out["close"].ewm(span=cfg.fast_ema, adjust=False).mean()
    out["ema_slow"] = out["close"].ewm(span=cfg.slow_ema, adjust=False).mean()
    prev_close = out["close"].shift(1)
    tr = pd.concat([(out["high"]-out["low"]), (out["high"]-prev_close).abs(), (out["low"]-prev_close).abs()], axis=1).max(axis=1)
    out["atr"] = tr.rolling(cfg.atr_window).mean()
    out["atr_pct"] = out["atr"] / out["close"] * 100.0
    # Shifted channel prevents the current candle from defining its own breakout.
    out["prior_high"] = out["high"].rolling(cfg.breakout_window).max().shift(1)
    out["prior_low"] = out["low"].rolling(cfg.breakout_window).min().shift(1)
    out["volume_ratio"] = out["volume"] / out["volume"].rolling(cfg.volume_window).mean().shift(1)
    return out


def signal_at(df: pd.DataFrame, index: int, cfg: TrendBreakoutConfig = TrendBreakoutConfig()) -> Signal:
    if index < max(cfg.slow_ema, cfg.breakout_window, cfg.atr_window, cfg.volume_window) + 1:
        return Signal("FLAT", 0.0, 0.0, 0.0, "warmup")
    row = indicators(df.iloc[: index + 1], cfg).iloc[-1]
    values = [row[c] for c in ("close", "ema_fast", "ema_slow", "atr", "atr_pct", "prior_high", "prior_low", "volume_ratio")]
    if any(pd.isna(v) for v in values):
        return Signal("FLAT", 0.0, 0.0, 0.0, "insufficient_data")
    if not cfg.min_atr_pct <= float(row["atr_pct"]) <= cfg.max_atr_pct:
        return Signal("FLAT", float(row["close"]), 0.0, 0.0, "volatility_filter")
    if float(row["volume_ratio"]) < cfg.min_volume_ratio:
        return Signal("FLAT", float(row["close"]), 0.0, 0.0, "volume_filter")
    price = float(row["close"]); atr = float(row["atr"])
    if price > float(row["prior_high"]) and float(row["ema_fast"]) > float(row["ema_slow"]):
        return Signal("LONG", price, cfg.stop_atr*atr, cfg.target_r*cfg.stop_atr*atr, "uptrend_donchian_breakout")
    if price < float(row["prior_low"]) and float(row["ema_fast"]) < float(row["ema_slow"]):
        return Signal("SHORT", price, cfg.stop_atr*atr, cfg.target_r*cfg.stop_atr*atr, "downtrend_donchian_breakout")
    return Signal("FLAT", price, 0.0, 0.0, "no_breakout")


def generate_signals(df: pd.DataFrame, cfg: TrendBreakoutConfig = TrendBreakoutConfig()) -> pd.DataFrame:
    data = indicators(df, cfg)
    rows = []
    for i, row in data.iterrows():
        if pd.isna(row["atr"]) or pd.isna(row["prior_high"]) or pd.isna(row["prior_low"]):
            rows.append(("FLAT", "warmup")); continue
        atr_pct = float(row["atr_pct"]); vol = float(row["volume_ratio"])
        if not cfg.min_atr_pct <= atr_pct <= cfg.max_atr_pct:
            rows.append(("FLAT", "volatility_filter")); continue
        if vol < cfg.min_volume_ratio:
            rows.append(("FLAT", "volume_filter")); continue
        if row["close"] > row["prior_high"] and row["ema_fast"] > row["ema_slow"]:
            rows.append(("LONG", "uptrend_donchian_breakout"))
        elif row["close"] < row["prior_low"] and row["ema_fast"] < row["ema_slow"]:
            rows.append(("SHORT", "downtrend_donchian_breakout"))
        else:
            rows.append(("FLAT", "no_breakout"))
    return pd.DataFrame(rows, index=data.index, columns=["direction", "reason"])
