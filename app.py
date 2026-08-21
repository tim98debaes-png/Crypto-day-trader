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
            (x.ema20_1h > x.ema50_1h)
            &
            (x.ema50_1h > x.ema200_1h)
            &
            (
                x.close
                <= x.ema20
                * (
                    1
                    + p.get(
                        "pullback_pct",
                        0.004,
                    )
                )
            )
            &
            (x.close >= x.ema50)
            &
            x.rsi.between(
                p.get(
                    "rsi_long_min",
                    45,
                ),
                p.get(
                    "rsi_long_max",
                    58,
                ),
            )
            &
            (
                x.macd_hist
                > x.macd_hist.shift(1)
            )
        )

        short_core = (
            (x.ema20_1h < x.ema50_1h)
            &
            (x.ema50_1h < x.ema200_1h)
            &
            (
                x.close
                >= x.ema20
                * (
                    1
                    - p.get(
                        "pullback_pct",
                        0.004,
                    )
                )
            )
            &
            (x.close <= x.ema50)
            &
            x.rsi.between(
                p.get(
                    "rsi_short_min",
                    42,
                ),
                p.get(
                    "rsi_short_max",
                    55,
                ),
            )
            &
            (
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

        long_core = (
            (x.bb_z <= -p.get("z_entry", 1.6))
            &
            (
                x.rsi
                <= p.get(
                    "rsi_oversold",
                    32,
                )
            )
            &
            (
                x.stoch_k
                < p.get(
                    "stoch_long",
                    25,
                )
            )
            &
            (x.close > x.close.shift(1))
        )

        short_core = (
            (x.bb_z >= p.get("z_entry", 1.6))
            &
            (
                x.rsi
                >= 100
                - p.get(
                    "rsi_oversold",
                    32,
                )
            )
            &
            (
                x.stoch_k
                > 100
                - p.get(
                    "stoch_long",
                    25,
                )
            )
            &
            (x.close < x.close.shift(1))
        )

        regime = (
            (x.adx <= p.get("adx_max", 24))
            &
            vol_ok
        )

        long_score = (
            long_core.astype(int) * 70
            + regime.astype(int) * 20
            + (
                x.vol_ratio
                >= p.get("vol_min", 0.8)
            ).astype(int) * 10
        )

        short_score = (
            short_core.astype(int) * 70
            + regime.astype(int) * 20
            + (
                x.vol_ratio
                >= p.get("vol_min", 0.8)
            ).astype(int) * 10
        )

    elif family == "momentum":

        long_core = (
            (
                x.ret3
                > p.get(
                    "ret3_min",
                    0.004,
                )
            )
            &
            (
                x.ret12
                > p.get(
                    "ret12_min",
                    0.008,
                )
            )
            &
            (x.macd_hist > 0)
            &
            (
                x.rsi
                > p.get(
                    "rsi_mom",
                    55,
                )
            )
        )

        short_core = (
            (
                x.ret3
                < -p.get(
                    "ret3_min",
                    0.004,
                )
            )
            &
            (
                x.ret12
                < -p.get(
                    "ret12_min",
                    0.008,
                )
            )
            &
            (x.macd_hist < 0)
            &
            (
                x.rsi
                < 100
                - p.get(
                    "rsi_mom",
                    55,
                )
            )
        )

        expansion = (
            (
                x.range_ratio
                >= p.get(
                    "range_ratio",
                    1.05,
                )
            )
            &
            (
                x.atr_pct_rank
                >= p.get(
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
# Metrics
# ============================================================

def metrics(pnls, equity, capital):

    p = np.asarray(
        pnls,
        dtype=float,
    )

    wins = (
        p[p > 0].sum()
        if len(p)
        else 0.0
    )

    losses = abs(
        p[p < 0].sum()
    ) if len(p) else 0.0

    pf = (
        wins / losses
        if losses
        else (
            np.inf
            if wins
            else 0.0
        )
    )

    wr = (
        (p > 0).mean() * 100
        if len(p)
        else 0.0
    )

    ret = (
        (equity[-1] / capital - 1)
        * 100
        if len(equity)
        else 0.0
    )

    dd = (
        np.min(
            equity
            / np.maximum.accumulate(equity)
            - 1
        )
        * 100
        if len(equity)
        else 0.0
    )

    expectancy = (
        float(np.mean(p))
        if len(p)
        else 0.0
    )

    std = (
        float(np.std(p, ddof=1))
        if len(p) > 1
        else 0.0
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

    negative = p[p < 0]

    downside = (
        float(
            np.std(
                negative,
                ddof=1,
            )
        )
        if len(negative) > 1
        else 0.0
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

    max_loss_streak = 0
    current = 0

    for value in p:

        if value < 0:
            current += 1
            max_loss_streak = max(
                max_loss_streak,
                current,
            )
        else:
            current = 0

    return {
        "return": float(ret),
        "pf": float(pf),
        "wr": float(wr),
        "dd": float(dd),
        "trades": int(len(p)),
        "expectancy": expectancy,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_loss_streak": int(
            max_loss_streak
        ),
    }


# ============================================================
# Backtest
# ============================================================

def backtest_direction(
    df,
    p,
    mode,
    capital,
    risk,
    fee,
    slip,
    direction,
    return_pnls=False,
):

    open_price = df.open.to_numpy(float)
    close = df.close.to_numpy(float)
    high = df.high.to_numpy(float)
    low = df.low.to_numpy(float)
    atr = df.atr.to_numpy(float)

    long_score, short_score = make_signals(
        df,
        p,
    )

    threshold = (
        p["threshold"]
        - (
            5
            if mode == "Agressief"
            else 0
        )
    )

    if direction == "LONG":

        signal = (
            (long_score >= threshold)
            &
            (
                long_score
                > short_score
                + p["min_edge"]
            )
        )

    else:

        signal = (
            (short_score >= threshold)
            &
            (
                short_score
                > long_score
                + p["min_edge"]
            )
        )

    cash = float(capital)

    position = 0
    entry = 0.0
    stop = 0.0
    tp = 0.0
    qty = 0.0
    age = 0
    risk_distance = 0.0
    best = 0.0

    pnls = []

    equity = np.empty(
        len(df),
        dtype=float,
    )

    equity[0] = cash

    for i in range(1, len(df)):

        # ----------------------------------------------------
        # Manage open position
        # ----------------------------------------------------

        if position != 0:

            age += 1

            exit_price = None

            if position == 1:

                best = max(
                    best,
                    high[i],
                )

                if (
                    best - entry
                    >= risk_distance
                    * p.get(
                        "trail_trigger_r",
                        1.0,
                    )
                ):
                    stop = max(
                        stop,
                        best
                        - atr[i]
                        * p.get(
                            "trail_atr",
                            1.0,
                        ),
                    )

                if low[i] <= stop:
                    exit_price = stop

                elif high[i] >= tp:
                    exit_price = tp

            else:

                best = min(
                    best,
                    low[i],
                )

                if (
                    entry - best
                    >= risk_distance
                    * p.get(
                        "trail_trigger_r",
                        1.0,
                    )
                ):
                    stop = min(
                        stop,
                        best
                        + atr[i]
                        * p.get(
                            "trail_atr",
                            1.0,
                        ),
                    )

                if high[i] >= stop:
                    exit_price = stop

                elif low[i] <= tp:
                    exit_price = tp

            if (
                exit_price is None
                and age >= p["max_bars"]
            ):
                exit_price = close[i]

            if exit_price is not None:

                if position == 1:

                    actual_exit = (
                        exit_price
                        * (
                            1
                            - slip / 100
                        )
                    )

                    gross = (
                        actual_exit
                        - entry
                    ) * qty

                else:

                    actual_exit = (
                        exit_price
                        * (
                            1
                            + slip / 100
                        )
                    )

                    gross = (
                        entry
                        - actual_exit
                    ) * qty

                fees = (
                    entry * qty
                    + actual_exit * qty
                ) * fee / 100

                pnl = gross - fees

                cash += pnl

                pnls.append(
                    float(pnl)
                )

                position = 0

        # ----------------------------------------------------
        # New position at NEXT candle open
        # ----------------------------------------------------

        if (
            position == 0
            and i + 1 < len(df)
            and signal[i - 1]
            and cash > 0
        ):

            if (
                np.isfinite(atr[i - 1])
                and atr[i - 1] > 0
            ):

                distance = max(
                    atr[i - 1]
                    * p["sl_atr"],
                    close[i - 1]
                    * p["min_stop_pct"]
                    / 100,
                )

                qty = (
                    cash
                    * risk
                    / 100
                    / distance
                )

                if direction == "LONG":

                    entry = (
                        open_price[i]
                        * (
                            1
                            + slip / 100
                        )
                    )

                    stop = (
                        entry
                        - distance
                    )

                    tp = (
                        entry
                        + distance
                        * p["rr"]
                    )

                    position = 1

                else:

                    entry = (
                        open_price[i]
                        * (
                            1
                            - slip / 100
                        )
                    )

                    stop = (
                        entry
                        + distance
                    )

                    tp = (
                        entry
                        - distance
                        * p["rr"]
                    )

                    position = -1

                risk_distance = distance
                best = entry
                age = 0

        equity[i] = cash

    result = metrics(
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

    p = np.asarray(
        pnls,
        dtype=float,
    )

    if len(p) < 15:

        return {
            "median_return": np.nan,
            "p05_return": np.nan,
            "p95_return": np.nan,
            "median_dd": np.nan,
            "p95_dd": np.nan,
        }

    rng = np.random.default_rng(seed)

    returns = np.empty(
        simulations
    )

    dds = np.empty(
        simulations
    )

    for j in range(simulations):

        sample = rng.choice(
            p,
            size=len(p),
            replace=True,
        )

        equity = (
            capital
            + np.cumsum(sample)
        )

        curve = np.r_[
            capital,
            equity,
        ]

        peak = np.maximum.accumulate(
            curve
        )

        dds[j] = np.min(
            (
                curve / peak
                - 1
            ) * 100
        )

        returns[j] = (
            eq_end_return := (
                equity[-1]
                / capital
                - 1
            )
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
            np.median(dds)
        ),
        "p95_dd": float(
            np.percentile(
                dds,
                95,
            )
        ),
    }


# ============================================================
# Improved parameter stability
# ============================================================

def build_stability_variants(p):

    family = p["family"]

    variants = []

    def add_variant(q):
        q = dict(q)
        variants.append(q)

    # --------------------------------------------------------
    # Risk / reward neighborhood
    # --------------------------------------------------------

    sl_values = sorted(
        set(
            [
                round(
                    max(
                        0.75,
                        p["sl_atr"] - 0.25,
                    ),
                    2,
                ),
                round(
                    p["sl_atr"],
                    2,
                ),
                round(
                    p["sl_atr"] + 0.25,
                    2,
                ),
            ]
        )
    )

    rr_values = sorted(
        set(
            [
                round(
                    max(
                        1.25,
                        p["rr"] - 0.25,
                    ),
                    2,
                ),
                round(
                    p["rr"],
                    2,
                ),
                round(
                    p["rr"] + 0.25,
                    2,
                ),
            ]
        )
    )

    threshold_values = sorted(
        set(
            [
                max(
                    55,
                    int(
                        p["threshold"]
                        - 10
                    ),
                ),
                int(p["threshold"]),
                min(
                    90,
                    int(
                        p["threshold"]
                        + 10
                    ),
                ),
            ]
        )
    )

    bars_values = sorted(
        set(
            [
                max(
                    18,
                    int(
                        p["max_bars"]
                        - 12
                    ),
                ),
                int(p["max_bars"]),
                min(
                    72,
                    int(
                        p["max_bars"]
                        + 12
                    ),
                ),
            ]
        )
    )

    # --------------------------------------------------------
    # Family-specific parameters
    # --------------------------------------------------------

    if family == "trend":

        rsi_pairs = [
            (
                max(
                    45,
                    p["rsi_min"] - 3,
                ),
                min(
                    75,
                    p["rsi_max"] - 3,
                ),
            ),
            (
                p["rsi_min"],
                p["rsi_max"],
            ),
            (
                min(
                    70,
                    p["rsi_min"] + 3,
                ),
                min(
                    80,
                    p["rsi_max"] + 3,
                ),
            ),
        ]

        for sl, rr, threshold, bars, pair in product(
            sl_values,
            rr_values,
            threshold_values,
            bars_values,
            rsi_pairs,
        ):

            q = dict(p)

            q["sl_atr"] = sl
            q["rr"] = rr
            q["threshold"] = threshold
            q["max_bars"] = bars
            q["rsi_min"] = pair[0]
            q["rsi_max"] = pair[1]

            add_variant(q)

    elif family == "momentum":

        momentum_values = [
            max(
                0.002,
                p["ret3_min"] * 0.75,
            ),
            p["ret3_min"],
            p["ret3_min"] * 1.25,
        ]

        for sl, rr, threshold, bars, mom in product(
            sl_values,
            rr_values,
            threshold_values,
            bars_values,
            momentum_values,
        ):

            q = dict(p)

            q["sl_atr"] = sl
            q["rr"] = rr
            q["threshold"] = threshold
            q["max_bars"] = bars
            q["ret3_min"] = mom
            q["ret12_min"] = mom * 2

            add_variant(q)

    elif family == "breakout":

        ranges = [
            max(
                1.05,
                p["range_ratio"] - 0.10,
            ),
            p["range_ratio"],
            p["range_ratio"] + 0.10,
        ]

        for sl, rr, threshold, bars, rng in product(
            sl_values,
            rr_values,
            threshold_values,
            bars_values,
            ranges,
        ):

            q = dict(p)

            q["sl_atr"] = sl
            q["rr"] = rr
            q["threshold"] = threshold
            q["max_bars"] = bars
            q["range_ratio"] = rng

            add_variant(q)

    elif family == "pullback":

        pullbacks = [
            max(
                0.002,
                p["pullback_pct"] - 0.002,
            ),
            p["pullback_pct"],
            p["pullback_pct"] + 0.002,
        ]

        for sl, rr, threshold, bars, pb in product(
            sl_values,
            rr_values,
            threshold_values,
            bars_values,
            pullbacks,
        ):

            q = dict(p)

            q["sl_atr"] = sl
            q["rr"] = rr
            q["threshold"] = threshold
            q["max_bars"] = bars
            q["pullback_pct"] = pb

            add_variant(q)

    elif family == "mean_reversion":

        z_values = [
            max(
                1.2,
                p["z_entry"] - 0.2,
            ),
            p["z_entry"],
            p["z_entry"] + 0.2,
        ]

        for sl, rr, threshold, bars, z in product(
            sl_values,
            rr_values,
            threshold_values,
            bars_values,
            z_values,
        ):

            q = dict(p)

            q["sl_atr"] = sl
            q["rr"] = rr
            q["threshold"] = threshold
            q["max_bars"] = bars
            q["z_entry"] = z

            add_variant(q)

    # Remove duplicates
    unique = []

    seen = set()

    for q in variants:

        key = json.dumps(
            q,
            sort_keys=True,
            default=str,
        )

        if key not in seen:
            seen.add(key)
            unique.append(q)

    return unique


def stability_score(
    df,
    p,
    mode,
    capital,
    risk,
    fee,
    slip,
):

    variants = build_stability_variants(p)

    if not variants:
        return {
            "score": 0.0,
            "valid": 0,
            "profitable": 0,
            "median_pf": 0.0,
            "median_return": 0.0,
            "worst_return": 0.0,
        }

    n = len(df)

    validation_folds = [
        (
            int(n * 0.35),
            int(n * 0.50),
        ),
        (
            int(n * 0.50),
            int(n * 0.65),
        ),
        (
            int(n * 0.65),
            int(n * 0.80),
        ),
    ]

    results = []

    for q in variants:

        fold_results = []

        for a, b in validation_folds:

            part = (
                df.iloc[a:b]
                .reset_index(drop=True)
            )

            r = backtest_direction(
                part,
                q,
                mode,
                capital,
                risk,
                fee,
                slip,
                q["direction"],
            )

            fold_results.append(r)

        trades = sum(
            r["trades"]
            for r in fold_results
        )

        avg_return = float(
            np.mean(
                [
                    r["return"]
                    for r in fold_results
                ]
            )
        )

        avg_pf = float(
            np.mean(
                [
                    min(
                        r["pf"],
                        3,
                    )
                    if np.isfinite(r["pf"])
                    else 3
                    for r in fold_results
                ]
            )
        )

        positive_folds = sum(
            r["return"] > 0
            for r in fold_results
        )

        good_pf_folds = sum(
            r["pf"] >= 1.0
            for r in fold_results
        )

        # A variant is considered usable if it has enough
        # validation trades to say something meaningful.
        if trades >= 9:

            results.append(
                {
                    "return": avg_return,
                    "pf": avg_pf,
                    "positive": positive_folds,
                    "pf_good": good_pf_folds,
                    "trades": trades,
                }
            )

    if not results:

        return {
            "score": 0.0,
            "valid": 0,
            "profitable": 0,
            "median_pf": 0.0,
            "median_return": 0.0,
            "worst_return": 0.0,
        }

    valid = len(results)

    # A robust variant should ideally be positive in at least
    # 2/3 validation folds and PF >= 1 in at least 2/3.
    profitable = sum(
        r["positive"] >= 2
        and r["pf_good"] >= 2
        and r["return"] > 0
        for r in results
    )

    score = (
        profitable / valid
    )

    median_pf = float(
        np.median(
            [
                r["pf"]
                for r in results
            ]
        )
    )

    median_return = float(
        np.median(
            [
                r["return"]
                for r in results
            ]
        )
    )

    worst_return = float(
        min(
            r["return"]
            for r in results
        )
    )

    return {
        "score": float(score),
        "valid": int(valid),
        "profitable": int(profitable),
        "median_pf": median_pf,
        "median_return": median_return,
        "worst_return": worst_return,
    }


# ============================================================
# Candidate evaluation
# ============================================================

def candidate_status(
    folds,
    oos,
    mc,
    stability,
):

    wf_good = sum(
        x["return"] > 0
        and x["pf"] >= 1.05
        for x in folds
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
        stability >= 0.60
    )

    confidence = round(
        min(
            wf_good / 3,
            1,
        ) * 25
        +
        min(
            max(
                oos["pf"] - 1,
                0,
            ),
            1,
        ) * 25
        +
        min(
            max(
                oos["return"],
                0,
            ) / 20,
            1,
        ) * 15
        +
        min(
            max(
                oos["dd"] + 20,
                0,
            ) / 20,
            1,
        ) * 10
        +
        min(
            max(
                mc["p05_return"],
                0,
            ) / 10,
            1,
        ) * 10
        +
        stability * 15,
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
        and stability >= 0.45
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

    if stability < 0.45:
        reasons.append(
            f"stability {stability:.0%} < 45%"
        )

    elif stability < 0.60:
        reasons.append(
            f"stability {stability:.0%} < 60%"
        )

    return (
        status,
        confidence,
        "; ".join(reasons)
        if reasons
        else "Alle hoofdcriteria gehaald",
    )


# ============================================================
# Strategy families
# ============================================================

STRATEGIES = []


# Trend
for sl_atr, rr in [
    (1.25, 1.5),
    (1.5, 2.0),
    (2.0, 2.5),
]:

    for threshold in [
        60,
        70,
        80,
    ]:

        for rsi_min, rsi_max in [
            (50, 65),
            (52, 68),
            (55, 70),
        ]:

            STRATEGIES.append(
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


# Breakout
for sl_atr, rr in [
    (1.25, 1.5),
    (1.5, 2.0),
    (2.0, 2.5),
]:

    for threshold in [
        60,
        70,
        80,
    ]:

        for rng in [
            1.10,
            1.25,
            1.40,
        ]:

            STRATEGIES.append(
                {
                    "family": "breakout",
                    "adx_min": 18,
                    "adx_htf": 18,
                    "vol_min": 1.0,
                    "vol_regime_min": 0.55,
                    "vol_regime_max": 3.0,
                    "range_ratio": rng,
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


# Pullback
for sl_atr, rr in [
    (1.25, 1.5),
    (1.5, 2.0),
    (2.0, 2.5),
]:

    for threshold in [
        60,
        70,
        80,
    ]:

        for pb in [
            0.003,
            0.005,
            0.008,
        ]:

            STRATEGIES.append(
                {
                    "family": "pullback",
                    "adx_min": 18,
                    "adx_htf": 18,
                    "vol_min": 0.8,
                    "vol_regime_min": 0.45,
                    "vol_regime_max": 2.5,
                    "pullback_pct": pb,
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


# Mean reversion
for sl_atr, rr in [
    (1.25, 1.5),
    (1.5, 2.0),
]:

    for threshold in [
        60,
        70,
    ]:

        for z in [
            1.5,
            1.8,
            2.1,
        ]:

            STRATEGIES.append(
                {
                    "family": "mean_reversion",
                    "adx_max": 24,
                    "vol_min": 0.8,
                    "vol_regime_min": 0.45,
                    "vol_regime_max": 1.5,
                    "z_entry": z,
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


# Momentum
for sl_atr, rr in [
    (1.25, 1.5),
    (1.5, 2.0),
    (2.0, 2.5),
]:

    for threshold in [
        60,
        70,
        80,
    ]:

        for mom in [
            0.003,
            0.005,
            0.008,
        ]:

            STRATEGIES.append(
                {
                    "family": "momentum",
                    "adx_min": 18,
                    "adx_htf": 18,
                    "vol_min": 1.0,
                    "vol_regime_min": 0.55,
                    "vol_regime_max": 3.0,
                    "ret3_min": mom,
                    "ret12_min": mom * 2,
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
# Strategy discovery
# ============================================================

def strategy_discovery(
    symbol,
    days,
    mode,
    capital,
    risk,
    fee,
    slip,
):

    data = build_mtf(
        symbol,
        int(days * 24 * 12),
    )

    if len(data) < 500:
        return {
            "Coin": symbol,
            "Status": "NO DATA",
        }

    n = len(data)

    final_oos = (
        data.iloc[int(n * 0.80):]
        .reset_index(drop=True)
    )

    candidates = []

    for p in STRATEGIES:

        for direction in [
            "LONG",
            "SHORT",
        ]:

            q = dict(p)
            q["direction"] = direction

            folds = []

            for a, b in [
                (
                    int(n * 0.35),
                    int(n * 0.50),
                ),
                (
                    int(n * 0.50),
                    int(n * 0.65),
                ),
                (
                    int(n * 0.65),
                    int(n * 0.80),
                ),
            ]:

                validation = (
                    data.iloc[a:b]
                    .reset_index(drop=True)
                )

                folds.append(
                    backtest_direction(
                        validation,
                        q,
                        mode,
                        capital,
                        risk,
                        fee,
                        slip,
                        direction,
                    )
                )

            total_trades = sum(
                x["trades"]
                for x in folds
            )

            if total_trades < 15:
                continue

            wf_good = sum(
                x["return"] > 0
                and x["pf"] >= 1.05
                for x in folds
            )

            avg_pf = np.mean(
                [
                    min(
                        x["pf"],
                        3,
                    )
                    if np.isfinite(x["pf"])
                    else 3
                    for x in folds
                ]
            )

            avg_ret = np.mean(
                [
                    x["return"]
                    for x in folds
                ]
            )

            discovery_score = (
                wf_good / 3 * 40
                +
                min(
                    avg_pf / 1.5,
                    1,
                ) * 25
                +
                min(
                    max(
                        avg_ret,
                        0,
                    ) / 15,
                    1,
                ) * 20
                +
                min(
                    total_trades / 45,
                    1,
                ) * 15
            )

            candidates.append(
                (
                    discovery_score,
                    q,
                    folds,
                )
            )

    if not candidates:
        return {
            "Coin": symbol,
            "Status": "NO EDGE",
        }

    candidates.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    best = None

    # Only the best validation candidates get
    # the more expensive stability calculation.
    for (
        discovery_score,
        p,
        folds,
    ) in candidates[:12]:

        stability_info = stability_score(
            data,
            p,
            mode,
            capital,
            risk,
            fee,
            slip,
        )

        stability = stability_info["score"]

        oos = backtest_direction(
            final_oos,
            p,
            mode,
            capital,
            risk,
            fee,
            slip,
            p["direction"],
            return_pnls=True,
        )

        mc = monte_carlo_stats(
            oos.get(
                "pnls",
                [],
            ),
            capital=capital,
            simulations=1000,
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
            1 if status == "WATCH" else 0,
            confidence,
            stability,
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
            discovery_score,
            p,
            folds,
            oos,
            mc,
            status,
            confidence,
            reason,
            stability_info,
        )

        if (
            best is None
            or rank > best[0]
        ):
            best = candidate

    (
        _rank,
        discovery_score,
        p,
        folds,
        oos,
        mc,
        status,
        confidence,
        reason,
        stability_info,
    ) = best

    opposite = (
        "SHORT"
        if p["direction"] == "LONG"
        else "LONG"
    )

    opposite_oos = backtest_direction(
        final_oos,
        p,
        mode,
        capital,
        risk,
        fee,
        slip,
        opposite,
    )

    return {
        "Coin": symbol,
        "Status": status,
        "Strategy": p["family"].upper(),
        "Direction": p["direction"],
        "Confidence": confidence,
        "Stability": round(
            stability_info["score"] * 100,
            1,
        ),
        "Valid variants": stability_info["valid"],
        "Stable variants": stability_info["profitable"],
        "Median stability PF": round(
            stability_info["median_pf"],
            3,
        ),
        "Discovery": round(
            float(discovery_score),
            1,
        ),
        "WF": (
            f"{sum("
            f"x['return'] > 0 "
            f"and x['pf'] >= 1.05 "
            f"for x in folds"
            f")}/3"
        ),
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
            3,
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
        "SL ATR": p["sl_atr"],
        "RR": p["rr"],
        "threshold": p["threshold"],
        "max bars": p["max_bars"],
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
):

    row = strategy_discovery(
        symbol,
        days,
        mode,
        capital,
        risk,
        fee,
        slip,
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
            if row.get("Status")
            == "TRADE"
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
    }


# ============================================================
# UI
# ============================================================

st.title(
    f"₿ Crypto DayTrader v{APP_VERSION}"
)

st.caption(
    "v8.4.2 • Trend / Breakout / Pullback / "
    "Mean-Reversion / Momentum • "
    "next-open execution • trailing stop • "
    "walk-forward • Monte Carlo • "
    "parameter-neighborhood stability"
)


# ============================================================
# Sidebar
# ============================================================

with st.sidebar:

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


current_config = make_config(
    days,
    mode,
    capital,
    risk,
    fee,
    slip,
)

store = load_store()

if (
    store["config"]
    != current_config
):

    active_results = {}

else:

    active_results = store[
        "results"
    ]


# ============================================================
# Tabs
# ============================================================

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

    done = sum(
        coin in active_results
        for coin in COINS
    )

    st.progress(
        done / len(COINS)
    )

    st.caption(
        f"{done}/{len(COINS)} coins opgeslagen"
    )

    c1, c2 = st.columns(2)

    with c1:

        start = st.button(
            "🚀 Start / hervat optimizer",
            type="primary",
        )

    with c2:

        reset = st.button(
            "🧹 Nieuwe optimalisatie"
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

        for i, symbol in enumerate(
            COINS
        ):

            if symbol in store[
                "results"
            ]:

                status_box.write(
                    f"✅ {symbol} al klaar — overslaan"
                )

                progress.progress(
                    (i + 1)
                    / len(COINS)
                )

                continue

            status_box.write(
                f"⚙️ {symbol}: robuustheidstest "
                f"({i + 1}/{len(COINS)})..."
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
                )

                store["results"][
                    symbol
                ] = {
                    "row": row,
                    "saved_at":
                        pd.Timestamp.utcnow()
                        .isoformat(),
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

                store["results"][
                    symbol
                ] = {
                    "row": row,
                    "saved_at":
                        pd.Timestamp.utcnow()
                        .isoformat(),
                }

                save_store(store)

                status_box.error(
                    f"{symbol}: {exc}"
                )

            progress.progress(
                (i + 1)
                / len(COINS)
            )

        st.success(
            "Robustness optimizer klaar."
        )

        st.rerun()

    rows = [
        x["row"]
        for x in active_results.values()
        if (
            isinstance(x, dict)
            and "row" in x
        )
    ]

    if rows:

        table = pd.DataFrame(
            rows
        )

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
            "Nog geen resultaten."
        )


# ============================================================
# Strategy Discovery
# ============================================================

with tab2:

    st.subheader(
        "🧠 Strategy Discovery v8.4.2"
    )

    st.write(
        "De engine onderzoekt meerdere strategie-families "
        "en richtingen. De laatste 20% van de data blijft "
        "onaangeraakte OOS-data. De nieuwe stability-test "
        "varieert parameters rond de gevonden kandidaat "
        "en gebruikt uitsluitend validation-data."
    )

    st.info(
        "Stability ≥60% = sterk • "
        "45–59% = WATCH-zone • "
        "<45% = instabiel"
    )

    discovery_key = (
        f"discovery_v842_"
        f"{days}_{mode}_{capital}_"
        f"{risk}_{fee}_{slip}"
    )

    if st.button(
        "🧠 Start Strategy Discovery",
        type="primary",
    ):

        discovery_rows = []

        progress = st.progress(0)

        message = st.empty()

        for i, symbol in enumerate(
            COINS
        ):

            message.write(
                f"🔎 Analyse {symbol} "
                f"({i + 1}/{len(COINS)})..."
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
                (i + 1)
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
            "TRADE vereist: ≥2/3 WF, ≥15 OOS-trades, "
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

        discovery = discovery.copy()

        if "Status" in discovery:

            discovery["_order"] = (
                discovery["Status"]
                .map(order)
                .fillna(9)
            )

            sort_col = (
                "Confidence"
                if "Confidence"
                in discovery.columns
                else "Coin"
            )

            discovery = (
                discovery
                .sort_values(
                    [
                        "_order",
                        sort_col,
                    ],
                    ascending=[
                        True,
                        False,
                    ],
                )
                .drop(
                    columns=[
                        "_order"
                    ]
                )
            )

        st.dataframe(
            discovery,
            use_container_width=True,
            hide_index=True,
        )

        trade_count = int(
            (
                discovery.get(
                    "Status",
                    pd.Series(
                        dtype=str
                    ),
                )
                == "TRADE"
            ).sum()
        )

        watch_count = int(
            (
                discovery.get(
                    "Status",
                    pd.Series(
                        dtype=str
                    ),
                )
                == "WATCH"
            ).sum()
        )

        if trade_count:

            st.success(
                f"🎯 {trade_count} kandidaat/kandidaten "
                "halen de TRADE-drempel."
            )

        elif watch_count:

            st.warning(
                f"🟡 {watch_count} kandidaat/kandidaten "
                "zitten in WATCH."
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
        x["row"]
        for x in active_results.values()
        if (
            isinstance(x, dict)
            and "row" in x
        )
    ]

    if rows:

        data = pd.DataFrame(
            rows
        )

        if "Status" in data:

            robust = data[
                data["Status"]
                .eq("ROBUST")
            ].copy()

        else:

            robust = pd.DataFrame()

        if len(robust):

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
            "Een kandidaat moet meerdere walk-forward "
            "periodes doorstaan én voldoende sterke "
            "finale OOS-resultaten hebben."
        )

    else:

        st.info(
            "Voer eerst de optimizer uit."
        )


# ============================================================
# Live scanner
# ============================================================

with tab4:

    st.subheader(
        "📈 Live scanner"
    )

    st.write(
        "Onderzoekssignalen op basis van de laatst "
        "gevonden strategie. Geen echte orders."
    )

    selected = st.multiselect(
        "Coins",
        COINS,
        default=COINS[:5],
    )

    if st.button(
        "🔎 Scan nu"
    ):

        scan = []

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

                family = str(
                    saved.get(
                        "Strategy",
                        "TREND",
                    )
                ).lower()

                # Reasonable generic defaults.
                p = {
                    "family": family,
                    "rsi_min": 52,
                    "rsi_max": 68,
                    "adx_min": 18,
                    "adx_htf": 18,
                    "vol_min": 1.0,
                    "vol_regime_min": 0.55,
                    "vol_regime_max": 2.8,
                    "slope_min": 0.02,
                    "sl_atr": float(
                        saved.get(
                            "SL ATR",
                            1.5,
                        )
                    ),
                    "rr": float(
                        saved.get(
                            "RR",
                            2.0,
                        )
                    ),
                    "threshold": int(
                        saved.get(
                            "threshold",
                            70,
                        )
                    ),
                    "min_edge": 5,
                    "max_bars": int(
                        saved.get(
                            "max bars",
                            48,
                        )
                    ),
                    "min_stop_pct": 0.35,
                    "trail_atr": 1.0,
                    "trail_trigger_r": 1.0,
                }

                # Family-specific defaults
                if family == "momentum":

                    p.update(
                        {
                            "ret3_min": 0.005,
                            "ret12_min": 0.010,
                            "rsi_mom": 55,
                            "range_ratio": 1.05,
                            "atr_rank": 0.55,
                        }
                    )

                elif family == "breakout":

                    p.update(
                        {
                            "range_ratio": 1.25,
                            "rsi_break_long": 55,
                            "rsi_break_short": 45,
                        }
                    )

                elif family == "pullback":

                    p.update(
                        {
                            "pullback_pct": 0.005,
                            "rsi_long_min": 45,
                            "rsi_long_max": 58,
                            "rsi_short_min": 42,
                            "rsi_short_max": 55,
                        }
                    )

                elif family == "mean_reversion":

                    p.update(
                        {
                            "adx_max": 24,
                            "vol_min": 0.8,
                            "vol_regime_min": 0.45,
                            "vol_regime_max": 1.5,
                            "z_entry": 1.8,
                            "rsi_oversold": 32,
                            "stoch_long": 25,
                            "adx_min": 0,
                            "adx_htf": 0,
                        }
                    )

                data = build_mtf(
                    symbol,
                    1000,
                )

                long_scores, short_scores = (
                    make_signals(
                        data,
                        p,
                    )
                )

                latest = data.iloc[-1]

                long_value = int(
                    long_scores[-1]
                )

                short_value = int(
                    short_scores[-1]
                )

                if (
                    long_value
                    >= p["threshold"]
                    and long_value
                    > short_value
                    + p["min_edge"]
                ):

                    raw_signal = "LONG"

                elif (
                    short_value
                    >= p["threshold"]
                    and short_value
                    > long_value
                    + p["min_edge"]
                ):

                    raw_signal = "SHORT"

                else:

                    raw_signal = "WAIT"

                allowed = (
                    saved.get(
                        "Status"
                    )
                    in {
                        "TRADE",
                        "WATCH",
                    }
                )

                saved_direction = saved.get(
                    "Direction"
                )

                if (
                    allowed
                    and raw_signal != "WAIT"
                    and (
                        not saved_direction
                        or saved_direction
                        == raw_signal
                    )
                ):

                    signal = raw_signal

                else:

                    signal = "WAIT"

                scan.append(
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
                            6,
                        ),
                    }
                )

            except Exception as exc:

                scan.append(
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
            pd.DataFrame(scan),
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# Footer
# ============================================================

st.divider()

st.warning(
    "Onderzoekstool. Geen financieel advies en geen live orders. "
    "Een positieve backtest is geen garantie voor toekomstige resultaten."
)