import json
import os
import time
from itertools import product

import numpy as np
import pandas as pd
import requests
import streamlit as st
from signal_engine import generate_signal
from paper_portfolio import PaperPortfolio
from market_feed import BinancePublicFeed
from validation_engine import (
    make_walk_forward_folds,
    summarize_validation,
    validation_score,
)


# ============================================================
# Crypto DayTrader v8.4.2
# ============================================================
# Research-only crypto strategy engine.
# - Binance public market data
# - 5m execution timeframe + 15m/1h closed-candle MTF filters
# - Trend / Breakout / Pullback / Mean Reversion / Momentum
# - Long and short evaluated independently
# - ATR SL/TP + trailing stop + time exit
# - 3-fold walk-forward validation
# - Final 20% untouched OOS test
# - Monte Carlo bootstrap
# - Parameter-neighbourhood stability
# - Autosave / resume
# - No live orders
# ============================================================

APP_VERSION = "8.5.0"
BINANCE = "https://data-api.binance.vision/api/v3/klines"

COINS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "DOTUSDT",
]

RESULTS_FILE = "optimizer_results_v850.json"

st.set_page_config(
    page_title=f"Crypto DayTrader v{APP_VERSION}",
    page_icon="₿",
    layout="wide",
)


# ============================================================
# Persistence
# ============================================================

def load_store():
    if not os.path.exists(RESULTS_FILE):
        return {"config": None, "results": {}}

    try:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {"config": None, "results": {}}

        data.setdefault("config", None)
        data.setdefault("results", {})
        return data

    except Exception:
        return {"config": None, "results": {}}


def save_store(store):
    tmp = RESULTS_FILE + ".tmp"

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(
            store,
            f,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    os.replace(tmp, RESULTS_FILE)


def make_config(days, mode, capital, risk, fee, slip, optimizer_mode="Volledig"):
    return {
        "days": int(days),
        "mode": str(mode),
        "capital": float(capital),
        "risk": float(risk),
        "fee": float(fee),
        "slip": float(slip),
        "optimizer_mode": str(optimizer_mode),
    }


# ============================================================
# Data
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def fetch(symbol, interval, limit):
    target = min(int(limit), 30000)
    rows = []
    end = None

    for _ in range(40):
        if len(rows) >= target:
            break

        n = min(1000, target - len(rows))

        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": n,
        }

        if end is not None:
            params["endTime"] = end

        batch = None
        last_error = None

        for retry in range(5):
            try:
                response = requests.get(
                    BINANCE,
                    params=params,
                    timeout=20,
                    headers={
                        "User-Agent": f"Crypto-DayTrader/{APP_VERSION}"
                    },
                )

                if response.status_code in (418, 429):
                    time.sleep(min(6, 2 ** retry))
                    continue

                response.raise_for_status()
                batch = response.json()
                break

            except Exception as exc:
                last_error = exc
                time.sleep(min(4, 1.5 ** retry))

        if batch is None:
            raise RuntimeError(
                f"Binance {symbol} {interval}: {last_error}"
            )

        if not batch:
            break

        rows = batch + rows
        end = batch[0][0] - 1

        if len(batch) < n:
            break

        time.sleep(0.05)

    if not rows:
        raise RuntimeError(
            f"Geen Binance-data voor {symbol} {interval}"
        )

    columns = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "qv",
        "trades",
        "tb",
        "tq",
        "ignore",
    ]

    data = pd.DataFrame(rows, columns=columns)
    data = data.drop_duplicates("open_time")

    numeric = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    for column in numeric:
        data[column] = pd.to_numeric(
            data[column],
            errors="coerce",
        )

    data["time"] = pd.to_datetime(
        data["open_time"],
        unit="ms",
        utc=True,
    )

    # Never feed an unfinished Binance candle into research/backtests.
    # The candle is considered closed only after close_time has passed.
    now_ms = int(time.time() * 1000)
    data["close_time"] = pd.to_numeric(
        data["close_time"],
        errors="coerce",
    )
    data = data[data["close_time"] <= now_ms]

    return (
        data.sort_values("time")
        [
            [
                "time",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        ]
        .dropna()
        .tail(target)
        .reset_index(drop=True)
    )


# ============================================================
# Indicators
# ============================================================

def ema(series, period):
    return series.ewm(
        span=period,
        adjust=False,
    ).mean()


def rsi(series, period=14):
    delta = series.diff()

    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)

    avg_up = up.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()

    avg_down = down.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()

    rs = avg_up / avg_down.replace(0, np.nan)

    return 100 - 100 / (1 + rs)


def adx(high, low, close, period=14):
    up = high.diff()
    down = -low.diff()

    plus_dm = np.where(
        (up > down) & (up > 0),
        up,
        0.0,
    )

    minus_dm = np.where(
        (down > up) & (down > 0),
        down,
        0.0,
    )

    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()

    plus_di = (
        100
        * pd.Series(
            plus_dm,
            index=high.index,
        ).ewm(
            alpha=1 / period,
            adjust=False,
        ).mean()
        / atr.replace(0, np.nan)
    )

    minus_di = (
        100
        * pd.Series(
            minus_dm,
            index=high.index,
        ).ewm(
            alpha=1 / period,
            adjust=False,
        ).mean()
        / atr.replace(0, np.nan)
    )

    dx = (
        100
        * (plus_di - minus_di).abs()
        / (plus_di + minus_di).replace(0, np.nan)
    )

    return dx.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()


def indicators(data):
    x = data.copy()

    x["ema9"] = ema(x.close, 9)
    x["ema20"] = ema(x.close, 20)
    x["ema50"] = ema(x.close, 50)
    x["ema200"] = ema(x.close, 200)

    x["rsi"] = rsi(x.close, 14)

    ema12 = ema(x.close, 12)
    ema26 = ema(x.close, 26)

    x["macd"] = ema12 - ema26
    x["macd_sig"] = ema(x.macd, 9)
    x["macd_hist"] = x.macd - x.macd_sig

    tr = pd.concat(
        [
            x.high - x.low,
            (x.high - x.close.shift()).abs(),
            (x.low - x.close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)

    x["atr"] = tr.ewm(
        alpha=1 / 14,
        adjust=False,
    ).mean()

    x["atr_pct"] = x.atr / x.close * 100
    x["adx"] = adx(x.high, x.low, x.close, 14)

    x["vol_ma"] = x.volume.rolling(20).mean()
    x["vol_ratio"] = (
        x.volume / x.vol_ma.replace(0, np.nan)
    )

    x["ret1"] = x.close.pct_change()
    x["ret3"] = x.close.pct_change(3)
    x["ret12"] = x.close.pct_change(12)

    x["volatility"] = x.ret1.rolling(20).std()
    x["volatility_ma"] = x.volatility.rolling(50).mean()

    x["vol_regime"] = (
        x.volatility
        / x.volatility_ma.replace(0, np.nan)
    )

    x["high20"] = (
        x.high.shift(1)
        .rolling(20)
        .max()
    )

    x["low20"] = (
        x.low.shift(1)
        .rolling(20)
        .min()
    )

    x["high55"] = (
        x.high.shift(1)
        .rolling(55)
        .max()
    )

    x["low55"] = (
        x.low.shift(1)
        .rolling(55)
        .min()
    )

    x["bb_mid"] = x.close.rolling(20).mean()
    x["bb_std"] = x.close.rolling(20).std()

    x["bb_z"] = (
        (x.close - x.bb_mid)
        / x.bb_std.replace(0, np.nan)
    )

    x["bb_width"] = (
        4 * x.bb_std
        / x.bb_mid.replace(0, np.nan)
    )

    x["ema20_slope"] = (
        x.ema20.pct_change(5) * 100
    )

    x["ema50_slope"] = (
        x.ema50.pct_change(10) * 100
    )

    x["momentum_accel"] = (
        x.ret3 - x.ret12 / 4
    )

    lowest = x.low.rolling(14).min()
    highest = x.high.rolling(14).max()

    x["stoch_k"] = (
        100
        * (x.close - lowest)
        / (highest - lowest).replace(0, np.nan)
    )

    x["stoch_d"] = x.stoch_k.rolling(3).mean()

    x["atr_pct_rank"] = (
        x.atr_pct.rolling(100).rank(pct=True)
    )

    x["range_pct"] = (
        (x.high - x.low)
        / x.close
        * 100
    )

    x["range_ratio"] = (
        x.range_pct
        / x.range_pct.rolling(20).mean().replace(
            0,
            np.nan,
        )
    )

    x["vol_breakout"] = (
        x.volume
        / x.volume.rolling(55).max().replace(
            0,
            np.nan,
        )
    )

    return x


@st.cache_data(ttl=300, show_spinner=False)
def build_mtf(symbol, limit):
    d5 = indicators(
        fetch(
            symbol,
            "5m",
            limit,
        )
    )

    d15 = indicators(
        fetch(
            symbol,
            "15m",
            min(
                10000,
                max(
                    500,
                    limit // 3 + 100,
                ),
            ),
        )
    )

    d1 = indicators(
        fetch(
            symbol,
            "1h",
            min(
                5000,
                max(
                    500,
                    limit // 12 + 100,
                ),
            ),
        )
    )

    def htf(data, suffix):
        selected = data[
            [
                "time",
                "close",
                "ema20",
                "ema50",
                "ema200",
                "rsi",
                "macd_hist",
                "adx",
                "atr_pct",
                "vol_ratio",
            ]
        ].copy()

        # Only use a higher-timeframe candle after it has closed.
        selected["available"] = selected.time.shift(-1)

        selected = selected.dropna(
            subset=["available"]
        )

        rename = {
            "close": f"close_{suffix}",
            "ema20": f"ema20_{suffix}",
            "ema50": f"ema50_{suffix}",
            "ema200": f"ema200_{suffix}",
            "rsi": f"rsi{suffix}",
            "macd_hist": f"macd{suffix}",
            "adx": f"adx{suffix}",
            "atr_pct": f"atrpct{suffix}",
            "vol_ratio": f"vol{suffix}",
        }

        return (
            selected
            .rename(columns=rename)
            .drop(columns=["time"])
        )

    out = pd.merge_asof(
        d5.sort_values("time"),
        htf(
            d15,
            "15",
        ).sort_values("available"),
        left_on="time",
        right_on="available",
        direction="backward",
    )

    out = pd.merge_asof(
        out.sort_values("time"),
        htf(
            d1,
            "1h",
        ).sort_values("available"),
        left_on="time",
        right_on="available",
        direction="backward",
    )

    required = [
        "atr",
        "adx",
        "ema20_15",
        "ema50_15",
        "ema200_15",
        "ema20_1h",
        "ema50_1h",
        "ema200_1h",
        "rsi15",
        "rsi1h",
        "adx15",
        "adx1h",
    ]

    missing = [
        column
        for column in required
        if column not in out.columns
    ]

    if missing:
        raise KeyError(
            f"MTF-kolommen ontbreken: {missing}"
        )

    return (
        out
        .dropna(subset=required)
        .reset_index(drop=True)
    )


# ============================================================
# Strategy definitions
# ============================================================

STRATEGIES = []


def add_strategy(params):
    STRATEGIES.append(dict(params))


for sl_atr, rr in product(
    [1.25, 1.5, 2.0],
    [1.5, 2.0, 2.5],
):
    for threshold in [60, 70, 80]:
        for rsi_min, rsi_max in [
            (50, 65),
            (52, 68),
            (55, 70),
        ]:
            add_strategy(
                {
                    "family": "trend",
                    "rsi_min": rsi_min,
                    "rsi_max": rsi_max,
                    "adx_min": 18,
                    "adx_htf": 18,
                    "vol_min": 1.0,
                    "vol_regime_min": 0.55,
                    "vol_regime_max": 2.8,
                    "slope_min": 0.02,
                    "sl_atr": sl_atr,
                    "rr": rr,
                    "threshold": threshold,
                    "min_edge": 8,
                    "max_bars": 48,
                    "min_stop_pct": 0.35,
                    "trail_atr": 1.0,
                    "trail_trigger_r": 1.0,
                }
            )


for sl_atr, rr in product(
    [1.25, 1.5, 2.0],
    [1.5, 2.0, 2.5],
):
    for threshold in [60, 70, 80]:
        for range_ratio in [1.10, 1.25, 1.40]:
            add_strategy(
                {
                    "family": "breakout",
                    "adx_min": 18,
                    "adx_htf": 18,
                    "vol_min": 1.0,
                    "vol_regime_min": 0.55,
                    "vol_regime_max": 3.0,
                    "range_ratio": range_ratio,
                    "rsi_break_long": 55,
                    "rsi_break_short": 45,
                    "sl_atr": sl_atr,
                    "rr": rr,
                    "threshold": threshold,
                    "min_edge": 5,
                    "max_bars": 36,
                    "min_stop_pct": 0.35,
                    "trail_atr": 1.1,
                    "trail_trigger_r": 1.0,
                }
            )


for sl_atr, rr in product(
    [1.25, 1.5, 2.0],
    [1.5, 2.0, 2.5],
):
    for threshold in [60, 70, 80]:
        for pullback_pct in [0.003, 0.005, 0.008]:
            add_strategy(
                {
                    "family": "pullback",
                    "adx_min": 18,
                    "adx_htf": 18,
                    "vol_min": 0.8,
                    "vol_regime_min": 0.45,
                    "vol_regime_max": 2.5,
                    "pullback_pct": pullback_pct,
                    "rsi_long_min": 45,
                    "rsi_long_max": 58,
                    "rsi_short_min": 42,
                    "rsi_short_max": 55,
                    "sl_atr": sl_atr,
                    "rr": rr,
                    "threshold": threshold,
                    "min_edge": 5,
                    "max_bars": 48,
                    "min_stop_pct": 0.30,
                    "trail_atr": 1.0,
                    "trail_trigger_r": 1.0,
                }
            )


for sl_atr, rr in product(
    [1.25, 1.5],
    [1.5, 2.0],
):
    for threshold in [60, 70]:
        for z_entry in [1.5, 1.8, 2.1]:
            add_strategy(
                {
                    "family": "mean_reversion",
                    "adx_max": 24,
                    "vol_min": 0.8,
                    "vol_regime_min": 0.45,
                    "vol_regime_max": 1.5,
                    "z_entry": z_entry,
                    "rsi_oversold": 32,
                    "stoch_long": 25,
                    "sl_atr": sl_atr,
                    "rr": rr,
                    "threshold": threshold,
                    "min_edge": 5,
                    "max_bars": 24,
                    "min_stop_pct": 0.30,
                    "trail_atr": 0.9,
                    "trail_trigger_r": 1.0,
                    "adx_min": 0,
                    "adx_htf": 0,
                }
            )


for sl_atr, rr in product(
    [1.25, 1.5, 2.0],
    [1.5, 2.0, 2.5],
):
    for threshold in [60, 70, 80]:
        for momentum in [0.003, 0.005, 0.008]:
            add_strategy(
                {
                    "family": "momentum",
                    "adx_min": 18,
                    "adx_htf": 18,
                    "vol_min": 1.0,
                    "vol_regime_min": 0.55,
                    "vol_regime_max": 3.0,
                    "ret3_min": momentum,
                    "ret12_min": momentum * 2,
                    "rsi_mom": 55,
                    "range_ratio": 1.05,
                    "atr_rank": 0.55,
                    "sl_atr": sl_atr,
                    "rr": rr,
                    "threshold": threshold,
                    "min_edge": 5,
                    "max_bars": 36,
                    "min_stop_pct": 0.35,
                    "trail_atr": 1.1,
                    "trail_trigger_r": 1.0,
                }
            )


# ============================================================
# Signals
# ============================================================

def make_signals(data, params):
    x = data
    family = params.get(
        "family",
        "trend",
    )

    adx_ok = (
        (x.adx >= params.get("adx_min", 18))
        & (
            x.adx1h
            >= params.get("adx_htf", 18)
        )
    )

    volume_ok = (
        x.vol_ratio
        >= params.get("vol_min", 1.0)
    )

    vol_ok = x.vol_regime.between(
        params.get(
            "vol_regime_min",
            0.55,
        ),
        params.get(
            "vol_regime_max",
            2.8,
        ),
    )

    if family == "trend":
        long_core = (
            (x.ema20_1h > x.ema50_1h)
            & (x.ema50_1h > x.ema200_1h)
            & (x.ema20_15 > x.ema50_15)
            & (
                x.ema20_slope
                > params.get(
                    "slope_min",
                    0.02,
                )
            )
            & x.rsi.between(
                params["rsi_min"],
                params["rsi_max"],
            )
            & (x.macd_hist > 0)
            & (x.ret3 > 0)
        )

        short_core = (
            (x.ema20_1h < x.ema50_1h)
            & (x.ema50_1h < x.ema200_1h)
            & (x.ema20_15 < x.ema50_15)
            & (
                x.ema20_slope
                < -params.get(
                    "slope_min",
                    0.02,
                )
            )
            & x.rsi.between(
                100 - params["rsi_max"],
                100 - params["rsi_min"],
            )
            & (x.macd_hist < 0)
            & (x.ret3 < 0)
        )

        long_score = (
            long_core.astype(int) * 55
            + adx_ok.astype(int) * 20
            + volume_ok.astype(int) * 10
            + vol_ok.astype(int) * 15
        )

        short_score = (
            short_core.astype(int) * 55
            + adx_ok.astype(int) * 20
            + volume_ok.astype(int) * 10
            + vol_ok.astype(int) * 15
        )

    elif family == "breakout":
        long_core = (
            (x.close > x.high55)
            & (x.ema20_15 > x.ema50_15)
            & (
                x.rsi
                > params.get(
                    "rsi_break_long",
                    55,
                )
            )
        )

        short_core = (
            (x.close < x.low55)
            & (x.ema20_15 < x.ema50_15)
            & (
                x.rsi
                < params.get(
                    "rsi_break_short",
                    45,
                )
            )
        )

        expansion = (
            x.range_ratio
            >= params.get(
                "range_ratio",
                1.15,
            )
        )

        long_score = (
            long_core.astype(int) * 60
            + expansion.astype(int) * 15
            + volume_ok.astype(int) * 15
            + adx_ok.astype(int) * 10
        )

        short_score = (
            short_core.astype(int) * 60
            + expansion.astype(int) * 15
            + volume_ok.astype(int) * 15
            + adx_ok.astype(int) * 10
        )

    elif family == "pullback":
        long_core = (
            (x.ema20_1h > x.ema50_1h)
            & (x.ema50_1h > x.ema200_1h)
            & (
                x.close
                <= x.ema20
                * (
                    1
                    + params.get(
                        "pullback_pct",
                        0.004,
                    )
                )
            )
            & (x.close >= x.ema50)
            & x.rsi.between(
                params.get(
                    "rsi_long_min",
                    45,
                ),
                params.get(
                    "rsi_long_max",
                    58,
                ),
            )
            & (
                x.macd_hist
                > x.macd_hist.shift(1)
            )
        )

        short_core = (
            (x.ema20_1h < x.ema50_1h)
            & (x.ema50_1h < x.ema200_1h)
            & (
                x.close
                >= x.ema20
                * (
                    1
                    - params.get(
                        "pullback_pct",
                        0.004,
                    )
                )
            )
            & (x.close <= x.ema50)
            & x.rsi.between(
                params.get(
                    "rsi_short_min",
                    42,
                ),
                params.get(
                    "rsi_short_max",
                    55,
                ),
            )
            & (
                x.macd_hist
                < x.macd_hist.shift(1)
            )
        )

        long_score = (
            long_core.astype(int) * 65
            + adx_ok.astype(int) * 20
            + volume_ok.astype(int) * 5
            + vol_ok.astype(int) * 10
        )

        short_score = (
            short_core.astype(int) * 65
            + adx_ok.astype(int) * 20
            + volume_ok.astype(int) * 5
            + vol_ok.astype(int) * 10
        )

    elif family == "mean_reversion":
        oversold = params.get(
            "rsi_oversold",
            32,
        )
        stoch_long = params.get(
            "stoch_long",
            25,
        )

        long_core = (
            (x.bb_z <= -params.get(
                "z_entry",
                1.6,
            ))
            & (x.rsi <= oversold)
            & (x.stoch_k < stoch_long)
            & (x.close > x.close.shift(1))
        )

        short_core = (
            (x.bb_z >= params.get(
                "z_entry",
                1.6,
            ))
            & (x.rsi >= 100 - oversold)
            & (x.stoch_k > 100 - stoch_long)
            & (x.close < x.close.shift(1))
        )

        regime = (
            (x.adx <= params.get(
                "adx_max",
                24,
            ))
            & vol_ok
        )

        long_score = (
            long_core.astype(int) * 70
            + regime.astype(int) * 20
            + (
                x.vol_ratio
                >= params.get(
                    "vol_min",
                    0.8,
                )
            ).astype(int) * 10
        )

        short_score = (
            short_core.astype(int) * 70
            + regime.astype(int) * 20
            + (
                x.vol_ratio
                >= params.get(
                    "vol_min",
                    0.8,
                )
            ).astype(int) * 10
        )

    elif family == "momentum":
        long_core = (
            (x.ret3 > params.get(
                "ret3_min",
                0.004,
            ))
            & (x.ret12 > params.get(
                "ret12_min",
                0.008,
            ))
            & (x.macd_hist > 0)
            & (
                x.rsi
                > params.get(
                    "rsi_mom",
                    55,
                )
            )
        )

        short_core = (
            (x.ret3 < -params.get(
                "ret3_min",
                0.004,
            ))
            & (x.ret12 < -params.get(
                "ret12_min",
                0.008,
            ))
            & (x.macd_hist < 0)
            & (
                x.rsi
                < 100 - params.get(
                    "rsi_mom",
                    55,
                )
            )
        )

        expansion = (
            (x.range_ratio >= params.get(
                "range_ratio",
                1.05,
            ))
            & (
                x.atr_pct_rank
                >= params.get(
                    "atr_rank",
                    0.55,
                )
            )
        )

        long_score = (
            long_core.astype(int) * 60
            + expansion.astype(int) * 15
            + volume_ok.astype(int) * 15
            + adx_ok.astype(int) * 10
        )

        short_score = (
            short_core.astype(int) * 60
            + expansion.astype(int) * 15
            + volume_ok.astype(int) * 15
            + adx_ok.astype(int) * 10
        )

    else:
        raise ValueError(
            f"Onbekende strategy family: {family}"
        )

    return (
        long_score.to_numpy(dtype=np.int16),
        short_score.to_numpy(dtype=np.int16),
    )


# ============================================================
# Backtest
# ============================================================

def calculate_metrics(
    pnls,
    equity,
    capital,
):
    p = np.asarray(
        pnls,
        dtype=float,
    )

    if len(p):
        wins = p[p > 0].sum()
        losses = abs(p[p < 0].sum())
        pf = (
            wins / losses
            if losses
            else (np.inf if wins else 0.0)
        )
        wr = float(
            (p > 0).mean() * 100
        )
        expectancy = float(
            np.mean(p)
        )
    else:
        pf = 0.0
        wr = 0.0
        expectancy = 0.0

    if len(equity):
        peak = np.maximum.accumulate(
            equity
        )
        dd = float(
            np.min(
                (equity / peak - 1) * 100
            )
        )
        ret = float(
            (equity[-1] / capital - 1)
            * 100
        )
    else:
        dd = 0.0
        ret = 0.0

    if len(p) > 1:
        std = float(
            np.std(
                p,
                ddof=1,
            )
        )
        sharpe = (
            float(
                np.mean(p)
                / std
                * np.sqrt(len(p))
            )
            if std > 0
            else 0.0
        )
    else:
        sharpe = 0.0

    negative = p[p < 0]

    if len(negative) > 1:
        downside = float(
            np.std(
                negative,
                ddof=1,
            )
        )
        sortino = (
            float(
                np.mean(p)
                / downside
                * np.sqrt(len(p))
            )
            if downside > 0
            else 0.0
        )
    else:
        sortino = 0.0

    streak = 0
    max_streak = 0

    for value in p:
        if value < 0:
            streak += 1
            max_streak = max(
                max_streak,
                streak,
            )
        else:
            streak = 0

    return {
        "return": ret,
        "pf": float(pf),
        "wr": wr,
        "dd": dd,
        "trades": int(len(p)),
        "expectancy": expectancy,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_loss_streak": int(
            max_streak
        ),
    }


def run_backtest(
    data,
    params,
    mode,
    capital,
    risk,
    fee,
    slip,
    direction,
    return_pnls=False,
):
    open_price = data.open.to_numpy(
        dtype=float
    )
    close = data.close.to_numpy(
        dtype=float
    )
    high = data.high.to_numpy(
        dtype=float
    )
    low = data.low.to_numpy(
        dtype=float
    )
    atr = data.atr.to_numpy(
        dtype=float
    )

    long_score, short_score = make_signals(
        data,
        params,
    )

    threshold = (
        params["threshold"]
        - (5 if mode == "Agressief" else 0)
    )

    if direction == "LONG":
        signal = (
            (long_score >= threshold)
            & (
                long_score
                > short_score
                + params["min_edge"]
            )
        )
    else:
        signal = (
            (short_score >= threshold)
            & (
                short_score
                > long_score
                + params["min_edge"]
            )
        )

    cash = float(capital)
    position = 0
    entry = 0.0
    stop = 0.0
    target = 0.0
    quantity = 0.0
    age = 0
    risk_distance = 0.0
    best = 0.0

    pnls = []

    equity = np.empty(
        len(data),
        dtype=float,
    )

    if len(equity):
        equity[0] = cash

    for i in range(1, len(data)):
        exited = False

        # ----------------------------------------------------
        # Manage open position
        # ----------------------------------------------------
        if position != 0:
            age += 1
            exit_price = None

            # Conservative intrabar handling:
            # evaluate the stop/target active at the candle open first.
            # A trailing stop is updated only after the candle survives,
            # so the current candle's high/low cannot retroactively move
            # the stop and then trigger it in the same candle.
            active_stop = stop

            if position == 1:
                if low[i] <= active_stop:
                    exit_price = active_stop
                elif high[i] >= target:
                    exit_price = target

                if exit_price is None:
                    best = max(best, high[i])
                    if (
                        best - entry
                        >= risk_distance
                        * params.get(
                            "trail_trigger_r",
                            1.0,
                        )
                    ):
                        stop = max(
                            stop,
                            best
                            - atr[i]
                            * params.get(
                                "trail_atr",
                                1.0,
                            ),
                        )

            else:
                if high[i] >= active_stop:
                    exit_price = active_stop
                elif low[i] <= target:
                    exit_price = target

                if exit_price is None:
                    best = min(best, low[i])
                    if (
                        entry - best
                        >= risk_distance
                        * params.get(
                            "trail_trigger_r",
                            1.0,
                        )
                    ):
                        stop = min(
                            stop,
                            best
                            + atr[i]
                            * params.get(
                                "trail_atr",
                                1.0,
                            ),
                        )

            if (
                exit_price is None
                and age >= params["max_bars"]
            ):
                exit_price = close[i]

            if exit_price is not None:
                if position == 1:
                    execution_exit = (
                        exit_price
                        * (1 - slip / 100)
                    )
                    gross = (
                        execution_exit - entry
                    ) * quantity
                else:
                    execution_exit = (
                        exit_price
                        * (1 + slip / 100)
                    )
                    gross = (
                        entry - execution_exit
                    ) * quantity

                fees = (
                    entry * quantity
                    + execution_exit * quantity
                ) * fee / 100

                pnl = gross - fees

                cash += pnl
                pnls.append(
                    float(pnl)
                )

                position = 0
                exited = True

        # ----------------------------------------------------
        # New position on next candle
        # ----------------------------------------------------
        if (
            position == 0
            and not exited
            and cash > 0
            and i + 1 < len(data)
            and signal[i - 1]
        ):
            previous_close = close[i - 1]
            previous_atr = atr[i - 1]

            if (
                np.isfinite(previous_atr)
                and previous_atr > 0
            ):
                distance = max(
                    previous_atr
                    * params["sl_atr"],
                    previous_close
                    * params["min_stop_pct"]
                    / 100,
                )

                quantity = (
                    cash
                    * risk
                    / 100
                    / distance
                )

                if direction == "LONG":
                    entry = (
                        open_price[i]
                        * (1 + slip / 100)
                    )
                    stop = entry - distance
                    target = (
                        entry
                        + distance
                        * params["rr"]
                    )
                    position = 1
                else:
                    entry = (
                        open_price[i]
                        * (1 - slip / 100)
                    )
                    stop = entry + distance
                    target = (
                        entry
                        - distance
                        * params["rr"]
                    )
                    position = -1

                risk_distance = distance
                best = entry
                age = 0

        if len(equity):
            if position == 0:
                equity[i] = cash
            else:
                if position == 1:
                    mark_price = close[i] * (1 - slip / 100)
                    unrealized = (mark_price - entry) * quantity
                else:
                    mark_price = close[i] * (1 + slip / 100)
                    unrealized = (entry - mark_price) * quantity

                estimated_exit_fees = (
                    entry * quantity
                    + mark_price * quantity
                ) * fee / 100

                equity[i] = (
                    cash
                    + unrealized
                    - estimated_exit_fees
                )

    # Force-close any position that is still open at the end of the
    # test period. Leaving it unrealized makes final return and trade
    # count depend on the arbitrary dataset boundary.
    if position != 0 and len(data):
        final_price = close[-1]

        if position == 1:
            execution_exit = final_price * (1 - slip / 100)
            gross = (execution_exit - entry) * quantity
        else:
            execution_exit = final_price * (1 + slip / 100)
            gross = (entry - execution_exit) * quantity

        fees = (
            entry * quantity
            + execution_exit * quantity
        ) * fee / 100

        pnl = gross - fees
        cash += pnl
        pnls.append(float(pnl))
        position = 0
        equity[-1] = cash

    result = calculate_metrics(
        pnls,
        equity,
        capital,
    )

    if return_pnls:
        result["pnls"] = np.asarray(
            pnls,
            dtype=float,
        )

    return result


# ============================================================
# Monte Carlo
# ============================================================

def monte_carlo_stats(
    pnls,
    capital=1000.0,
    simulations=1000,
    seed=42,
):
    values = np.asarray(
        pnls,
        dtype=float,
    )

    if len(values) < 15:
        return {
            "median_return": np.nan,
            "p05_return": np.nan,
            "p95_return": np.nan,
            "median_dd": np.nan,
            "p95_dd": np.nan,
        }

    rng = np.random.default_rng(
        seed
    )

    returns = np.empty(
        simulations
    )

    drawdowns = np.empty(
        simulations
    )

    for index in range(simulations):
        sample = rng.choice(
            values,
            size=len(values),
            replace=True,
        )

        equity = capital + np.cumsum(
            sample
        )

        curve = np.r_[
            capital,
            equity,
        ]

        peak = np.maximum.accumulate(
            curve
        )

        drawdowns[index] = np.min(
            (curve / peak - 1) * 100
        )

        returns[index] = (
            equity[-1] / capital - 1
        ) * 100

    return {
        "median_return": float(
            np.median(returns)
        ),
        "p05_return": float(
            np.percentile(
                returns,
                5,
            )
        ),
        "p95_return": float(
            np.percentile(
                returns,
                95,
            )
        ),
        "median_dd": float(
            np.median(drawdowns)
        ),
        "p95_dd": float(
            np.percentile(
                drawdowns,
                95,
            )
        ),
    }


# ============================================================
# Stability
# ============================================================

def make_neighbours(params):
    family = params["family"]
    base = dict(params)

    neighbours = []

    def add_variant(**changes):
        item = dict(base)
        item.update(changes)
        neighbours.append(item)

    if family == "trend":
        values = [
            max(
                50,
                params["rsi_min"] - 2,
            ),
            params["rsi_min"],
            min(
                60,
                params["rsi_min"] + 2,
            ),
        ]

        for rsi_value in values:
            add_variant(
                rsi_min=rsi_value,
                rsi_max=max(
                    rsi_value + 12,
                    params["rsi_max"],
                ),
            )

        add_variant(
            sl_atr=max(
                1.0,
                params["sl_atr"] - 0.25,
            )
        )

        add_variant(
            sl_atr=params["sl_atr"] + 0.25
        )

        add_variant(
            rr=max(
                1.25,
                params["rr"] - 0.25,
            )
        )

        add_variant(
            rr=params["rr"] + 0.25
        )

        add_variant(
            threshold=max(
                55,
                params["threshold"] - 5,
            )
        )

        add_variant(
            threshold=min(
                85,
                params["threshold"] + 5,
            )
        )

    elif family == "breakout":
        add_variant(
            range_ratio=max(
                1.05,
                params["range_ratio"] - 0.10,
            )
        )

        add_variant(
            range_ratio=params["range_ratio"] + 0.10
        )

        add_variant(
            sl_atr=max(
                1.0,
                params["sl_atr"] - 0.25,
            )
        )

        add_variant(
            sl_atr=params["sl_atr"] + 0.25
        )

        add_variant(
            rr=max(
                1.25,
                params["rr"] - 0.25,
            )
        )

        add_variant(
            rr=params["rr"] + 0.25
        )

    elif family == "pullback":
        add_variant(
            pullback_pct=max(
                0.002,
                params["pullback_pct"] - 0.001,
            )
        )

        add_variant(
            pullback_pct=params["pullback_pct"] + 0.001
        )

        add_variant(
            sl_atr=max(
                1.0,
                params["sl_atr"] - 0.25,
            )
        )

        add_variant(
            sl_atr=params["sl_atr"] + 0.25
        )

        add_variant(
            rr=max(
                1.25,
                params["rr"] - 0.25,
            )
        )

        add_variant(
            rr=params["rr"] + 0.25
        )

    elif family == "mean_reversion":
        add_variant(
            z_entry=max(
                1.3,
                params["z_entry"] - 0.2,
            )
        )

        add_variant(
            z_entry=params["z_entry"] + 0.2
        )

        add_variant(
            rsi_oversold=max(
                28,
                params["rsi_oversold"] - 2,
            )
        )

        add_variant(
            rsi_oversold=min(
                36,
                params["rsi_oversold"] + 2,
            )
        )

        add_variant(
            sl_atr=max(
                1.0,
                params["sl_atr"] - 0.25,
            )
        )

        add_variant(
            sl_atr=params["sl_atr"] + 0.25
        )

    elif family == "momentum":
        add_variant(
            ret3_min=max(
                0.002,
                params["ret3_min"] - 0.001,
            ),
            ret12_min=max(
                0.004,
                params["ret12_min"] - 0.002,
            ),
        )

        add_variant(
            ret3_min=params["ret3_min"] + 0.001,
            ret12_min=params["ret12_min"] + 0.002,
        )

        add_variant(
            sl_atr=max(
                1.0,
                params["sl_atr"] - 0.25,
            )
        )

        add_variant(
            sl_atr=params["sl_atr"] + 0.25
        )

        add_variant(
            rr=max(
                1.25,
                params["rr"] - 0.25,
            )
        )

        add_variant(
            rr=params["rr"] + 0.25
        )

    # Always include the original.
    neighbours.insert(
        0,
        dict(base),
    )

    unique = []
    seen = set()

    for item in neighbours:
        key = json.dumps(
            item,
            sort_keys=True,
            default=str,
        )

        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def strategy_stability(
    data,
    params,
    mode,
    capital,
    risk,
    fee,
    slip,
):
    variants = make_neighbours(
        params
    )

    scores = []

    n = len(data)

    validation_folds = make_walk_forward_folds(n)

    for variant in variants:
        fold_results = []

        for _train_start, _train_end, valid_start, valid_end in validation_folds:
            subset = data.iloc[
                valid_start:valid_end
            ].reset_index(drop=True)

            result = run_backtest(
                subset,
                variant,
                mode,
                capital,
                risk,
                fee,
                slip,
                variant["direction"],
            )

            fold_results.append(
                result
            )

        valid = (
            sum(
                result["return"] > 0
                and result["pf"] >= 1.0
                for result in fold_results
            )
            >= 2
        )

        scores.append(
            {
                "valid": bool(valid),
                "pf": float(
                    np.mean(
                        [
                            min(
                                result["pf"],
                                3,
                            )
                            if np.isfinite(
                                result["pf"]
                            )
                            else 3
                            for result in fold_results
                        ]
                    )
                ),
            }
        )

    if not scores:
        return {
            "score": 0.0,
            "valid": 0,
            "profitable": 0,
            "median_pf": 0.0,
        }

    profitable = sum(
        item["valid"]
        for item in scores
    )

    median_pf = float(
        np.median(
            [
                item["pf"]
                for item in scores
            ]
        )
    )

    return {
        "score": float(
            profitable / len(scores)
        ),
        "valid": len(scores),
        "profitable": int(
            profitable
        ),
        "median_pf": median_pf,
    }


# ============================================================
# Candidate selection
# ============================================================

def candidate_status(
    folds,
    oos,
    mc,
    stability,
):
    wf_good = sum(
        result["return"] > 0
        and result["pf"] >= 1.05
        for result in folds
    )

    hard_oos = (
        oos["trades"] >= 15
        and oos["return"] > 0
        and oos["pf"] >= 1.20
        and oos["dd"] > -20
    )

    mc_ok = (
        np.isfinite(
            mc["p05_return"]
        )
        and mc["p05_return"] > -10
    )

    stable_ok = (
        stability["score"] >= 0.60
    )

    confidence = round(
        min(
            wf_good / 3,
            1,
        ) * 25
        + min(
            max(
                oos["pf"] - 1,
                0,
            ),
            1,
        ) * 25
        + min(
            max(
                oos["return"],
                0,
            )
            / 20,
            1,
        ) * 15
        + min(
            max(
                oos["dd"] + 20,
                0,
            )
            / 20,
            1,
        ) * 10
        + min(
            max(
                mc["p05_return"]
                if np.isfinite(
                    mc["p05_return"]
                )
                else 0,
                0,
            )
            / 10,
            1,
        ) * 10
        + stability["score"] * 15,
        1,
    )

    if (
        wf_good >= 2
        and hard_oos
        and mc_ok
        and stable_ok
    ):
        status = "TRADE"
    elif (
        oos["return"] > 0
        and oos["pf"] >= 1.05
        and oos["trades"] >= 10
        and stability["score"] >= 0.45
    ):
        status = "WATCH"
    else:
        status = "NO TRADE"

    reasons = []

    if wf_good < 2:
        reasons.append(
            f"WF {wf_good}/3"
        )

    if oos["trades"] < 15:
        reasons.append(
            f"OOS trades {oos['trades']} < 15"
        )

    if oos["pf"] < 1.20:
        reasons.append(
            f"OOS PF {oos['pf']:.2f} < 1.20"
        )

    if oos["return"] <= 0:
        reasons.append(
            "OOS rendement <= 0"
        )

    if oos["dd"] <= -20:
        reasons.append(
            f"OOS DD {oos['dd']:.1f}%"
        )

    if not mc_ok:
        reasons.append(
            "MC P05 < -10%"
        )

    if not stable_ok:
        reasons.append(
            "stability "
            f"{stability['score']:.0%} < 60%"
        )

    reason = (
        "; ".join(reasons)
        if reasons
        else "Alle hoofdcriteria gehaald"
    )

    return (
        status,
        confidence,
        reason,
    )


def discovery_score(
    folds,
):
    if not folds:
        return 0.0

    wf_good = sum(
        result["return"] > 0
        and result["pf"] >= 1.05
        for result in folds
    )

    avg_pf = np.mean(
        [
            min(
                result["pf"],
                3,
            )
            if np.isfinite(
                result["pf"]
            )
            else 3
            for result in folds
        ]
    )

    avg_return = np.mean(
        [
            result["return"]
            for result in folds
        ]
    )

    total_trades = sum(
        result["trades"]
        for result in folds
    )

    return float(
        wf_good / 3 * 40
        + min(
            avg_pf / 1.5,
            1,
        ) * 25
        + min(
            max(
                avg_return,
                0,
            )
            / 15,
            1,
        ) * 20
        + min(
            total_trades / 45,
            1,
        ) * 15
    )


def strategy_discovery(
    symbol,
    days,
    mode,
    capital,
    risk,
    fee,
    slip,
    optimizer_mode="Volledig",
):
    limit = int(
        days * 24 * 12
    )

    data = build_mtf(
        symbol,
        limit,
    )

    if len(data) < 500:
        return {
            "Coin": symbol,
            "Status": "NO DATA",
            "Reason": "Te weinig data",
        }

    n = len(data)

    validation_folds = make_walk_forward_folds(n)
    if not validation_folds:
        return {
            "Coin": symbol,
            "Status": "NO DATA",
            "Reason": "Te weinig data voor walk-forward validatie",
        }

    final_oos_start = int(n * 0.80)
    final_oos = data.iloc[
        final_oos_start:
    ].reset_index(drop=True)

    candidates = []

    strategy_pool = (
        STRATEGIES
        if optimizer_mode == "Volledig"
        else fast_strategy_pool()
    )

    for base in strategy_pool:
        for direction in [
            "LONG",
            "SHORT",
        ]:
            params = dict(base)
            params["direction"] = direction

            folds = []

            for _train_start, _train_end, valid_start, valid_end in validation_folds:
                subset = data.iloc[
                    valid_start:valid_end
                ].reset_index(drop=True)

                result = run_backtest(
                    subset,
                    params,
                    mode,
                    capital,
                    risk,
                    fee,
                    slip,
                    direction,
                )

                folds.append(result)

            total_trades = sum(
                result["trades"]
                for result in folds
            )

            if total_trades < 15:
                continue

            validation_summary = summarize_validation(
                folds
            )
            score = validation_score(
                validation_summary
            )

            candidates.append(
                (
                    score,
                    params,
                    folds,
                )
            )

    if not candidates:
        return {
            "Coin": symbol,
            "Status": "NO EDGE",
            "Reason": "Geen voldoende actieve kandidaat",
        }

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    best = None

    max_candidates = 3 if optimizer_mode == "Snel" else 12

    for score, params, folds in candidates[:max_candidates]:
        stability = strategy_stability(
            data,
            params,
            mode,
            capital,
            risk,
            fee,
            slip,
        )

        oos = run_backtest(
            final_oos,
            params,
            mode,
            capital,
            risk,
            fee,
            slip,
            params["direction"],
            return_pnls=True,
        )

        mc = monte_carlo_stats(
            oos.get(
                "pnls",
                [],
            ),
            capital=capital,
            simulations=(300 if optimizer_mode == "Snel" else 1000),
        )

        status, confidence, reason = (
            candidate_status(
                folds,
                oos,
                mc,
                stability,
            )
        )

        rank = (
            1 if status == "TRADE" else 0,
            confidence,
            stability["score"],
            (
                oos["pf"]
                if np.isfinite(
                    oos["pf"]
                )
                else 3
            ),
            oos["return"],
        )

        candidate = (
            rank,
            score,
            params,
            folds,
            oos,
            mc,
            status,
            confidence,
            reason,
            stability,
        )

        if (
            best is None
            or rank > best[0]
        ):
            best = candidate

    (
        _rank,
        best_score,
        params,
        folds,
        oos,
        mc,
        status,
        confidence,
        reason,
        stability,
    ) = best

    opposite = (
        "SHORT"
        if params["direction"] == "LONG"
        else "LONG"
    )

    opposite_oos = run_backtest(
        final_oos,
        params,
        mode,
        capital,
        risk,
        fee,
        slip,
        opposite,
    )

    wf_count = sum(
        1
        for result in folds
        if result["return"] > 0
        and result["pf"] >= 1.05
    )

    return {
        "Coin": symbol,
        "Status": status,
        "Strategy": params["family"].upper(),
        "Direction": params["direction"],
        "Confidence": confidence,
        "Stability": round(
            stability["score"] * 100,
            1,
        ),
        "Valid variants": stability["valid"],
        "Stable variants": stability["profitable"],
        "Median stability PF": round(
            stability["median_pf"],
            3,
        ),
        "Discovery": round(
            float(best_score),
            1,
        ),
        "WF": f"{wf_count}/3",
        "OOS PF": round(
            oos["pf"],
            3,
        ),
        "OOS %": round(
            oos["return"],
            2,
        ),
        "OOS trades": oos["trades"],
        "OOS WR": round(
            oos["wr"],
            2,
        ),
        "OOS DD": round(
            oos["dd"],
            2,
        ),
        "Expectancy": round(
            oos["expectancy"],
            4,
        ),
        "Sharpe": round(
            oos["sharpe"],
            2,
        ),
        "Sortino": round(
            oos["sortino"],
            2,
        ),
        "Max loss streak": oos[
            "max_loss_streak"
        ],
        "Opposite PF": round(
            opposite_oos["pf"],
            3,
        ),
        "MC P05 %": (
            round(
                mc["p05_return"],
                2,
            )
            if np.isfinite(
                mc["p05_return"]
            )
            else np.nan
        ),
        "MC median %": (
            round(
                mc["median_return"],
                2,
            )
            if np.isfinite(
                mc["median_return"]
            )
            else np.nan
        ),
        "MC P95 DD": (
            round(
                mc["p95_dd"],
                2,
            )
            if np.isfinite(
                mc["p95_dd"]
            )
            else np.nan
        ),
        "Reason": reason,
        "SL ATR": params["sl_atr"],
        "RR": params["rr"],
        "threshold": params["threshold"],
        "max bars": params["max_bars"],
        "Strategy Params": dict(params),
    }


# ============================================================
# Optimizer wrapper
# ============================================================

def optimize_coin(
    symbol,
    days,
    mode,
    capital,
    risk,
    fee,
    slip,
    optimizer_mode="Volledig",
):
    row = strategy_discovery(
        symbol,
        days,
        mode,
        capital,
        risk,
        fee,
        slip,
        optimizer_mode,
    )

    if row.get("Status") in {
        "ERROR",
        "NO DATA",
        "NO EDGE",
    }:
        return {
            "Coin": symbol,
            "Status": "AFGEKEURD",
            "Reason": row.get(
                "Reason",
                "Geen edge",
            ),
        }

    return {
        "Coin": symbol,
        "Status": (
            "ROBUST"
            if row.get("Status") == "TRADE"
            else "AFGEKEURD"
        ),
        "Robustness": row.get(
            "Confidence",
            0,
        ),
        "Strategy": row.get(
            "Strategy"
        ),
        "Direction": row.get(
            "Direction"
        ),
        "Stability": row.get(
            "Stability"
        ),
        "WF consistency": row.get(
            "WF"
        ),
        "OOS PF": row.get(
            "OOS PF"
        ),
        "OOS %": row.get(
            "OOS %"
        ),
        "OOS trades": row.get(
            "OOS trades"
        ),
        "OOS WR": row.get(
            "OOS WR"
        ),
        "OOS DD": row.get(
            "OOS DD"
        ),
        "Expectancy": row.get(
            "Expectancy"
        ),
        "Sharpe": row.get(
            "Sharpe"
        ),
        "Sortino": row.get(
            "Sortino"
        ),
        "Max loss streak": row.get(
            "Max loss streak"
        ),
        "MC P05 %": row.get(
            "MC P05 %"
        ),
        "Reason": row.get(
            "Reason"
        ),
        "SL ATR": row.get(
            "SL ATR"
        ),
        "RR": row.get(
            "RR"
        ),
        "threshold": row.get(
            "threshold"
        ),
        "max bars": row.get(
            "max bars"
        ),
        "Strategy Params": row.get(
            "Strategy Params"
        ),
    }


# ============================================================
# UI
# ============================================================

st.title(
    f"₿ Crypto DayTrader v{APP_VERSION}"
)

st.caption(
    "Trend / Breakout / Pullback / Mean-Reversion / Momentum • "
    "5m + 15m + 1h • next-open execution • WF • OOS • "
    "Monte Carlo • parameter stability"
)


with st.sidebar:
    st.header("⚙️ Onderzoeksinstellingen")

    mode = st.radio(
        "Strategie",
        [
            "Conservatief",
            "Agressief",
        ],
    )

    capital = st.number_input(
        "Startkapitaal (€)",
        100.0,
        100000.0,
        1000.0,
        100.0,
    )

    risk = st.slider(
        "Risico per trade (%)",
        0.25,
        2.0,
        1.0,
        0.25,
    )

    fee = st.number_input(
        "Fee per kant (%)",
        0.0,
        0.50,
        0.10,
        0.01,
    )

    slip = st.number_input(
        "Slippage per kant (%)",
        0.0,
        0.50,
        0.03,
        0.01,
    )

    days = st.select_slider(
        "Onderzoeksperiode",
        options=[
            14,
            30,
            60,
            90,
        ],
        value=60,
    )

    optimizer_mode = st.radio(
        "Optimalisatiesnelheid",
        ["Snel", "Volledig"],
        index=0,
        help=(
            "Snel test een representatieve set van alle 5 strategie-families "
            "en 3 beste kandidaten. Volledig test de volledige parameter-grid."
        ),
    )


current_config = make_config(
    days,
    mode,
    capital,
    risk,
    fee,
    slip,
    optimizer_mode,
)

store = load_store()

if store["config"] != current_config:
    active_results = {}
else:
    active_results = store["results"]


tab1, tab2, tab3, tab4 = st.tabs(
    [
        "🔬 Optimizer",
        "🧠 Strategy Discovery",
        "🏆 Robustness",
        "📈 Live scanner",
    ]
)


# ============================================================
# Optimizer
# ============================================================

with tab1:
    st.subheader(
        "🔬 Robustness Optimizer"
    )

    done = sum(
        coin in active_results
        for coin in COINS
    )

    st.progress(
        done / len(COINS)
    )

    st.caption(
        f"{done}/{len(COINS)} coins opgeslagen • "
        f"modus: {optimizer_mode}"
    )

    col1, col2 = st.columns(2)

    with col1:
        start = st.button(
            "🚀 Start / hervat optimizer",
            type="primary",
            key="optimizer_start",
        )

    with col2:
        reset = st.button(
            "🧹 Nieuwe optimalisatie",
            key="optimizer_reset",
        )

    if reset:
        store = {
            "config": current_config,
            "results": {},
        }

        save_store(store)
        st.rerun()

    if start:
        store = {
            "config": current_config,
            "results": active_results,
        }

        progress = st.progress(
            done / len(COINS)
        )

        status_box = st.empty()

        for index, symbol in enumerate(
            COINS
        ):
            if symbol in store["results"]:
                status_box.write(
                    f"✅ {symbol} al klaar — overslaan"
                )

                progress.progress(
                    (index + 1)
                    / len(COINS)
                )

                continue

            status_box.write(
                f"⚙️ {symbol}: "
                f"robustheidstest "
                f"({index + 1}/{len(COINS)})..."
            )

            started = time.time()

            try:
                row = optimize_coin(
                    symbol,
                    days,
                    mode,
                    capital,
                    risk,
                    fee,
                    slip,
                    optimizer_mode,
                )

                store["results"][symbol] = {
                    "row": row,
                    "saved_at": (
                        pd.Timestamp.utcnow()
                        .isoformat()
                    ),
                }

                save_store(store)

                elapsed = (
                    time.time()
                    - started
                )

                status_box.write(
                    f"✅ {symbol} klaar in "
                    f"{elapsed:.1f}s — opgeslagen"
                )

            except Exception as exc:
                row = {
                    "Coin": symbol,
                    "Status": "FOUT",
                    "Reason": str(exc),
                }

                store["results"][symbol] = {
                    "row": row,
                    "saved_at": (
                        pd.Timestamp.utcnow()
                        .isoformat()
                    ),
                }

                save_store(store)

                status_box.error(
                    f"{symbol}: {exc}"
                )

            progress.progress(
                (index + 1)
                / len(COINS)
            )

        st.success(
            "Robustness optimizer klaar."
        )

        st.rerun()

    rows = [
        item["row"]
        for item in active_results.values()
        if isinstance(item, dict)
        and "row" in item
    ]

    if rows:
        table = pd.DataFrame(rows)

        if "Robustness" in table.columns:
            table = table.sort_values(
                "Robustness",
                ascending=False,
                na_position="last",
            )

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(
            "Nog geen optimizer-resultaten."
        )


# ============================================================
# Strategy Discovery
# ============================================================
# ============================================================
# Optimizer performance modes
# ============================================================


def fast_strategy_pool():
    """Small representative pool for fast research.

    Fast mode reduces the parameter search space, but keeps all five
    strategy families and evaluates LONG/SHORT independently.
    The strict TRADE/WATCH/NO TRADE rules remain unchanged.
    """
    return [
        {
            "family": "trend",
            "rsi_min": 52, "rsi_max": 68,
            "adx_min": 18, "adx_htf": 18,
            "vol_min": 1.0, "vol_regime_min": 0.55,
            "vol_regime_max": 2.8, "slope_min": 0.02,
            "sl_atr": 1.5, "rr": 2.0, "threshold": 70,
            "min_edge": 8, "max_bars": 48,
            "min_stop_pct": 0.35, "trail_atr": 1.0,
            "trail_trigger_r": 1.0,
        },
        {
            "family": "breakout",
            "adx_min": 18, "adx_htf": 18,
            "vol_min": 1.0, "vol_regime_min": 0.55,
            "vol_regime_max": 3.0, "range_ratio": 1.25,
            "rsi_break_long": 55, "rsi_break_short": 45,
            "sl_atr": 1.5, "rr": 2.0, "threshold": 70,
            "min_edge": 5, "max_bars": 36,
            "min_stop_pct": 0.35, "trail_atr": 1.1,
            "trail_trigger_r": 1.0,
        },
        {
            "family": "pullback",
            "adx_min": 18, "adx_htf": 18,
            "vol_min": 0.8, "vol_regime_min": 0.45,
            "vol_regime_max": 2.5, "pullback_pct": 0.005,
            "rsi_long_min": 45, "rsi_long_max": 58,
            "rsi_short_min": 42, "rsi_short_max": 55,
            "sl_atr": 1.5, "rr": 2.0, "threshold": 70,
            "min_edge": 5, "max_bars": 48,
            "min_stop_pct": 0.30, "trail_atr": 1.0,
            "trail_trigger_r": 1.0,
        },
        {
            "family": "mean_reversion",
            "adx_min": 0, "adx_htf": 0, "adx_max": 24,
            "vol_min": 0.8, "vol_regime_min": 0.45,
            "vol_regime_max": 1.5, "z_entry": 1.8,
            "rsi_oversold": 32, "stoch_long": 25,
            "sl_atr": 1.5, "rr": 2.0, "threshold": 70,
            "min_edge": 5, "max_bars": 24,
            "min_stop_pct": 0.30, "trail_atr": 0.9,
            "trail_trigger_r": 1.0,
        },
        {
            "family": "momentum",
            "adx_min": 18, "adx_htf": 18,
            "vol_min": 1.0, "vol_regime_min": 0.55,
            "vol_regime_max": 3.0, "ret3_min": 0.005,
            "ret12_min": 0.010, "rsi_mom": 55,
            "range_ratio": 1.05, "atr_rank": 0.55,
            "sl_atr": 1.5, "rr": 2.0, "threshold": 70,
            "min_edge": 5, "max_bars": 36,
            "min_stop_pct": 0.35, "trail_atr": 1.1,
            "trail_trigger_r": 1.0,
        },
    ]



with tab2:
    st.subheader(
        "🧠 Strategy Discovery"
    )

    st.write(
        "De engine onderzoekt meerdere strategie-families "
        "en beide richtingen. De laatste 20% van de data "
        "blijft onaangeroerd tot de finale OOS-test."
    )

    discovery_key = (
        "discovery_v842_"
        f"{days}_"
        f"{mode}_"
        f"{capital}_"
        f"{risk}_"
        f"{fee}_"
        f"{slip}"
    )

    if st.button(
        "🧠 Start Strategy Discovery",
        type="primary",
        key="discovery_start",
    ):
        discovery_rows = []

        progress = st.progress(
            0
        )

        message = st.empty()

        for index, symbol in enumerate(
            COINS
        ):
            message.write(
                f"🔎 Analyse {symbol} "
                f"({index + 1}/{len(COINS)})..."
            )

            try:
                discovery_rows.append(
                    strategy_discovery(
                        symbol,
                        days,
                        mode,
                        capital,
                        risk,
                        fee,
                        slip,
                        optimizer_mode,
                    )
                )

            except Exception as exc:
                discovery_rows.append(
                    {
                        "Coin": symbol,
                        "Status": "ERROR",
                        "Reason": str(exc),
                    }
                )

            progress.progress(
                (index + 1)
                / len(COINS)
            )

        st.session_state[
            discovery_key
        ] = pd.DataFrame(
            discovery_rows
        )

    discovery = st.session_state.get(
        discovery_key
    )

    if discovery is not None:
        st.caption(
            "TRADE vereist ≥2/3 WF, ≥15 OOS-trades, "
            "OOS PF ≥1.20, positief OOS-rendement, "
            "DD > -20%, MC P05 > -10% en ≥60% "
            "parameter-stability."
        )

        order = {
            "TRADE": 0,
            "WATCH": 1,
            "NO TRADE": 2,
            "NO EDGE": 3,
            "NO DATA": 4,
            "ERROR": 5,
        }

        display = discovery.copy()

        if "Status" in display.columns:
            display["_order"] = (
                display["Status"]
                .map(order)
                .fillna(9)
            )

            sort_column = (
                "OOS PF"
                if "OOS PF" in display.columns
                else "Coin"
            )

            display = (
                display
                .sort_values(
                    [
                        "_order",
                        sort_column,
                    ],
                    ascending=[
                        True,
                        False,
                    ],
                )
                .drop(
                    columns=["_order"]
                )
            )

        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
        )

        trade_count = int(
            (
                discovery["Status"]
                == "TRADE"
            ).sum()
        )

        watch_count = int(
            (
                discovery["Status"]
                == "WATCH"
            ).sum()
        )

        if trade_count:
            st.success(
                f"{trade_count} kandidaat/kandidaten "
                "halen de TRADE-drempel."
            )
        elif watch_count:
            st.warning(
                f"{watch_count} kandidaat/kandidaten "
                "zijn WATCH, maar geen enkele is "
                "sterk genoeg voor TRADE."
            )
        else:
            st.info(
                "Geen robuuste edge gevonden. "
                "Dat is een geldig resultaat."
            )


# ============================================================
# Robustness
# ============================================================

with tab3:
    st.subheader(
        "🏆 Robuuste strategieën"
    )

    rows = [
        item["row"]
        for item in active_results.values()
        if isinstance(item, dict)
        and "row" in item
    ]

    if rows:
        table = pd.DataFrame(
            rows
        )

        if "Status" in table.columns:
            robust = table[
                table["Status"]
                == "ROBUST"
            ].copy()
        else:
            robust = pd.DataFrame()

        if len(robust):
            robust = robust.sort_values(
                "Robustness",
                ascending=False,
                na_position="last",
            )

            st.success(
                f"{len(robust)} coin(s) "
                "hebben een robuuste kandidaat."
            )

            st.dataframe(
                robust,
                use_container_width=True,
                hide_index=True,
            )

        else:
            st.warning(
                "Geen robuuste strategie gevonden. "
                "De optimizer forceert geen winnaar."
            )

        st.info(
            "Een kandidaat moet meerdere "
            "walk-forward periodes doorstaan "
            "én sterke finale OOS-resultaten hebben."
        )

    else:
        st.info(
            "Voer eerst de optimizer uit."
        )


# ============================================================
# Live Scanner
# ============================================================

with tab4:
    st.subheader(
        "📈 Live scanner"
    )

    st.write(
        "Onderzoekssignalen op basis van de laatst "
        "gevonden strategie. Er worden geen echte "
        "orders geplaatst."
    )

    selected = st.multiselect(
        "Coins",
        COINS,
        default=COINS[:5],
        key="scanner_coins",
    )

    if st.button(
        "🔎 Scan nu",
        key="scanner_scan",
    ):
        scan_rows = []

        for symbol in selected:
            try:
                saved = (
                    active_results
                    .get(
                        symbol,
                        {},
                    )
                    .get(
                        "row",
                        {},
                    )
                )

                params = saved.get("Strategy Params")

                if not isinstance(params, dict):
                    scan_rows.append(
                        {
                            "Coin": symbol,
                            "Signal": "WAIT",
                            "Strategy": saved.get("Strategy", "-"),
                            "Long": 0,
                            "Short": 0,
                            "Reason": "Geen volledige geoptimaliseerde parameters opgeslagen; opnieuw optimaliseren vereist.",
                        }
                    )
                    continue

                params = dict(params)
                family = str(
                    params.get(
                        "family",
                        saved.get("Strategy", "TREND"),
                    )
                ).lower()
                params["family"] = family
                params["direction"] = saved.get(
                    "Direction",
                    params.get("direction", "LONG"),
                )

                data = build_mtf(
                    symbol,
                    1000,
                )

                long_scores, short_scores = (
                    make_signals(
                        data,
                        params,
                    )
                )

                latest = data.iloc[-1]

                long_value = int(
                    long_scores[-1]
                )

                short_value = int(
                    short_scores[-1]
                )

                candidate = dict(saved)
                candidate["signal_threshold"] = params.get(
                    "threshold", 70
                )
                candidate["rr"] = params.get(
                    "rr", 2.0
                )

                signal_result = generate_signal(
                    candidate,
                    {
                        "long_score": long_value,
                        "short_score": short_value,
                        "stop_distance": float(latest.atr)
                        * float(params.get("sl_atr", 1.5)),
                        "rr": float(params.get("rr", 2.0)),
                    },
                )

                signal = signal_result.action

                saved_direction = saved.get("Direction")
                if (
                    signal in {"LONG", "SHORT"}
                    and saved_direction
                    and saved_direction != signal
                ):
                    signal = "WAIT"

                scan_rows.append(
                    {
                        "Coin": symbol,
                        "Signal": signal,
                        "Strategy": family.upper(),
                        "Long": long_value,
                        "Short": short_value,
                        "ADX": round(
                            float(
                                latest.adx
                            ),
                            1,
                        ),
                        "RSI": round(
                            float(
                                latest.rsi
                            ),
                            1,
                        ),
                        "Vol ratio": round(
                            float(
                                latest.vol_ratio
                            ),
                            2,
                        ),
                        "Price": round(
                            float(
                                latest.close
                            ),
                            8,
                        ),
                    }
                )

            except Exception as exc:
                scan_rows.append(
                    {
                        "Coin": symbol,
                        "Signal": "ERROR",
                        "Strategy": "-",
                        "Long": 0,
                        "Short": 0,
                        "Error": str(exc),
                    }
                )

        st.dataframe(
            pd.DataFrame(
                scan_rows
            ),
            use_container_width=True,
            hide_index=True,
        )


# ---------------- Phase 5 Paper Trading Dashboard ----------------
with st.expander("📊 Phase 5 — Paper Trading", expanded=False):
    st.caption("Simulation only • publieke marktdata • geen live orders")

    if "phase5_portfolio" not in st.session_state:
        st.session_state.phase5_portfolio = PaperPortfolio(
            capital=capital,
            risk_pct=risk,
            fee_pct=fee,
            slippage_pct=slip,
        )

    if "phase5_feed" not in st.session_state:
        st.session_state.phase5_feed = BinancePublicFeed()

    symbols = st.multiselect(
        "Paper-symbolen",
        COINS,
        default=COINS[:3],
        key="phase5_symbols",
    )

    if st.button("🔄 Marktdata vernieuwen", key="phase5_refresh"):
        st.rerun()

    marks = {}
    for symbol in symbols:
        try:
            marks[symbol] = st.session_state.phase5_feed.snapshot(symbol).price
        except Exception as exc:
            st.warning(f"{symbol}: marktdata niet beschikbaar ({exc})")

    summary = st.session_state.phase5_portfolio.summary(marks)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Equity", f"€{summary['equity']:,.2f}")
    c2.metric("Open posities", summary["open_positions"])
    c3.metric("Closed trades", summary["closed_trades"])
    c4.metric("Winrate", f"{summary['win_rate_pct']:.1f}%")

    if marks:
        st.dataframe(
            pd.DataFrame(
                [{"Symbol": symbol, "Price": price} for symbol, price in marks.items()]
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.info("De koppeling van gevalideerde optimizer-signalen naar automatische paper entries blijft actief via de Phase-5 execution engine.")

# ============================================================
# Footer
# ============================================================

st.divider()

st.warning(
    "Onderzoekstool. Geen financieel advies en geen live orders. "
    "Een positieve backtest is geen garantie voor toekomstige resultaten."
)

st.caption(
    f"Crypto DayTrader v{APP_VERSION} • "
    f"{len(STRATEGIES)} strategy parameter sets"
)
