import json
import os
import time
from itertools import product

import numpy as np
import pandas as pd
import requests
import streamlit as st


# ============================================================
# Crypto DayTrader v8.4.2
# Robust strategy research engine
#
# v8.4.2 changes:
# - Improved parameter-neighborhood stability test
# - Stability is measured on validation data only
# - Final 20% remains untouched OOS
# - Consistent next-open execution
# - Trailing stop + time exit
# - Long / short independently tested
# - Walk-forward validation
# - Monte Carlo bootstrap
# - Autosave / resume
# - No live orders
# ============================================================

APP_VERSION = "8.4.2"

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

RESULTS_FILE = "optimizer_results_v842.json"


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


def make_config(days, mode, capital, risk, fee, slip):
    return {
        "days": int(days),
        "mode": str(mode),
        "capital": float(capital),
        "risk": float(risk),
        "fee": float(fee),
        "slip": float(slip),
        "version": APP_VERSION,
    }


# ============================================================
# Binance data
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def fetch(symbol, interval, limit):
    target = min(int(limit), 30000)

    rows = []
    end = None

    for _ in range(30):

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

    cols = [
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

    data = pd.DataFrame(rows, columns=cols)

    data = data.drop_duplicates("open_time")

    for col in [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]:
        data[col] = pd.to_numeric(
            data[col],
            errors="coerce",
        )

    data["time"] = pd.to_datetime(
        data.open_time,
        unit="ms",
        utc=True,
    )

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

def ema(series, n):
    return series.ewm(
        span=n,
        adjust=False,
    ).mean()


def rsi(series, n=14):
    delta = series.diff()

    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)

    avg_up = up.ewm(
        alpha=1 / n,
        adjust=False,
    ).mean()

    avg_down = down.ewm(
        alpha=1 / n,
        adjust=False,
    ).mean()

    rs = avg_up / avg_down.replace(0, np.nan)

    return 100 - 100 / (1 + rs)


def adx(high, low, close, n=14):

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
        alpha=1 / n,
        adjust=False,
    ).mean()

    plus_di = (
        100
        * pd.Series(
            plus_dm,
            index=high.index,
        ).ewm(
            alpha=1 / n,
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
            alpha=1 / n,
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
        alpha=1 / n,
        adjust=False,
    ).mean()


def indicators(data):

    x = data.copy()

    x["ema9"] = ema(x.close, 9)
    x["ema20"] = ema(x.close, 20)
    x["ema50"] = ema(x.close, 50)
    x["ema200"] = ema(x.close, 200)

    x["rsi"] = rsi(x.close, 14)

    e12 = ema(x.close, 12)
    e26 = ema(x.close, 26)

    x["macd"] = e12 - e26
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

    x["adx"] = adx(
        x.high,
        x.low,
        x.close,
        14,
    )

    x["vol_ma"] = x.volume.rolling(20).mean()

    x["vol_ratio"] = (
        x.volume
        / x.vol_ma.replace(0, np.nan)
    )

    x["ret1"] = x.close.pct_change()
    x["ret3"] = x.close.pct_change(3)
    x["ret12"] = x.close.pct_change(12)

    x["volatility"] = (
        x.ret1.rolling(20).std()
    )

    x["volatility_ma"] = (
        x.volatility.rolling(50).mean()
    )

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

    low14 = x.low.rolling(14).min()
    high14 = x.high.rolling(14).max()

    x["stoch_k"] = (
        100
        * (x.close - low14)
        / (high14 - low14).replace(
            0,
            np.nan,
        )
    )

    x["stoch_d"] = (
        x.stoch_k.rolling(3).mean()
    )

    x["atr_pct_rank"] = (
        x.atr_pct
        .rolling(100)
        .rank(pct=True)
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
        fetch(symbol, "5m", limit)
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

        z = data[
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

        z["available"] = z.time.shift(-1)

        z = z.dropna(
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
            z.rename(columns=rename)
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
        col
        for col in required
        if col not in out.columns
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
# Strategy signals
# ============================================================

def make_signals(df, p):

    x = df
    family = p.get(
        "family",
        "trend",
    )

    adx_ok = (
        (x.adx >= p.get("adx_min", 18))
        &
        (x.adx1h >= p.get("adx_htf", 18))
    )

    volume_ok = (
        x.vol_ratio
        >= p.get("vol_min", 1.0)
    )

    vol_ok = x.vol_regime.between(
        p.get("vol_regime_min", 0.55),
        p.get("vol_regime_max", 2.8),
    )

    if family == "trend":

        long_core = (
            (x.ema20_1h > x.ema50_1h)
            &
            (x.ema50_1h > x.ema200_1h)
            &
            (x.ema20_15 > x.ema50_15)
            &
            (
                x.ema20_slope
                > p.get("slope_min", 0.02)
            )
            &
            x.rsi.between(
                p["rsi_min"],
                p["rsi_max"],
            )
            &
            (x.macd_hist > 0)
            &
            (x.ret3 > 0)
        )

        short_core = (
            (x.ema20_1h < x.ema50_1h)
            &
            (x.ema50_1h < x.ema200_1h)
            &
            (x.ema20_15 < x.ema50_15)
            &
            (
                x.ema20_slope
                < -p.get("slope_min", 0.02)
            )
            &
            x.rsi.between(
                100 - p["rsi_max"],
                100 - p["rsi_min"],
            )
            &
            (x.macd_hist < 0)
            &
            (x.ret3 < 0)
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
            &
            (x.ema20_15 > x.ema50_15)
            &
            (
                x.rsi
                > p.get(
                    "rsi_break_long",
                    55,
                )
            )
        )

        short_core = (
            (x.close < x.low55)
            &
            (x.ema20_15 < x.ema50_15)
            &
            (
                x.rsi
                < p.get(
                    "rsi_break_short",
                    45,
                )
            )
        )

        expansion = (
            x.range_ratio
            >= p.get(
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
            (x.ema