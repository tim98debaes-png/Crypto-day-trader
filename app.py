import json
import os
import time

import numpy as np
import pandas as pd
import requests
import streamlit as st


# ============================================================
# Crypto DayTrader v8.4.1
# ============================================================
# Research engine only — no live orders
#
# Features:
# - 5m execution timeframe
# - 15m + 1h higher timeframe confirmation
# - Long / Short independently tested
# - Trend strategy
# - Breakout strategy
# - Pullback strategy
# - Mean-reversion strategy
# - Momentum strategy
# - ATR stop loss
# - Risk/reward TP
# - ATR trailing stop
# - Time exit
# - Realistic next-open execution
# - Fees + slippage
# - 3-fold walk-forward validation
# - Untouched 20% final OOS
# - Parameter stability
# - Monte Carlo using actual trade P&Ls
# - Autosave after every coin
# - Optimizer
# - Strategy Discovery
# - Robustness overview
# - Scanner
# ============================================================

APP_VERSION = "8.4.1"

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

RESULTS_FILE = "optimizer_results_v841.json"


# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title=f"Crypto DayTrader v{APP_VERSION}",
    page_icon="₿",
    layout="wide",
)


# ============================================================
# PERSISTENCE
# ============================================================

def empty_store():
    return {
        "config": None,
        "results": {},
    }


def load_store():
    if not os.path.exists(RESULTS_FILE):
        return empty_store()

    try:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return empty_store()

        data.setdefault("config", None)
        data.setdefault("results", {})

        return data

    except Exception:
        return empty_store()


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
    }


# ============================================================
# DATA
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
                    time.sleep(min(8, 2 ** retry))
                    continue

                response.raise_for_status()

                batch = response.json()
                break

            except Exception as exc:
                last_error = exc
                time.sleep(min(5, 1.5 ** retry))

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
        "quote_volume",
        "trades",
        "taker_base",
        "taker_quote",
        "ignore",
    ]

    data = pd.DataFrame(
        rows,
        columns=columns,
    ).drop_duplicates("open_time")

    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]:
        data[column] = pd.to_numeric(
            data[column],
            errors="coerce",
        )

    data["time"] = pd.to_datetime(
        data["open_time"],
        unit="ms",
        utc=True,
    )

    data = (
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

    return data


# ============================================================
# INDICATORS
# ============================================================

def ema(series, period):
    return series.ewm(
        span=period,
        adjust=False,
    ).mean()


def rsi(series, period=14):
    delta = series.diff()

    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    avg_gain = gains.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()

    avg_loss = losses.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()

    rs = avg_gain / avg_loss.replace(
        0,
        np.nan,
    )

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

    true_range = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = true_range.ewm(
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
        / (plus_di + minus_di).replace(
            0,
            np.nan,
        )
    )

    return dx.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()


def indicators(data):

    x = data.copy()

    # Trend
    x["ema9"] = ema(x["close"], 9)
    x["ema20"] = ema(x["close"], 20)
    x["ema50"] = ema(x["close"], 50)
    x["ema200"] = ema(x["close"], 200)

    # RSI
    x["rsi"] = rsi(x["close"], 14)

    # MACD
    ema12 = ema(x["close"], 12)
    ema26 = ema(x["close"], 26)

    x["macd"] = ema12 - ema26
    x["macd_signal"] = ema(x["macd"], 9)
    x["macd_hist"] = (
        x["macd"] - x["macd_signal"]
    )

    # ATR
    true_range = pd.concat(
        [
            x["high"] - x["low"],
            (x["high"] - x["close"].shift()).abs(),
            (x["low"] - x["close"].shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)

    x["atr"] = true_range.ewm(
        alpha=1 / 14,
        adjust=False,
    ).mean()

    x["atr_pct"] = (
        x["atr"] / x["close"] * 100
    )

    # ADX
    x["adx"] = adx(
        x["high"],
        x["low"],
        x["close"],
        14,
    )

    # Volume
    x["volume_ma"] = (
        x["volume"].rolling(20).mean()
    )

    x["volume_ratio"] = (
        x["volume"]
        / x["volume_ma"].replace(0, np.nan)
    )

    # Returns
    x["ret1"] = x["close"].pct_change()
    x["ret3"] = x["close"].pct_change(3)
    x["ret12"] = x["close"].pct_change(12)

    # Volatility
    x["volatility"] = (
        x["ret1"].rolling(20).std()
    )

    x["volatility_ma"] = (
        x["volatility"].rolling(50).mean()
    )

    x["vol_regime"] = (
        x["volatility"]
        / x["volatility_ma"].replace(0, np.nan)
    )

    # Breakouts
    x["high20"] = (
        x["high"]
        .shift(1)
        .rolling(20)
        .max()
    )

    x["low20"] = (
        x["low"]
        .shift(1)
        .rolling(20)
        .min()
    )

    x["high55"] = (
        x["high"]
        .shift(1)
        .rolling(55)
        .max()
    )

    x["low55"] = (
        x["low"]
        .shift(1)
        .rolling(55)
        .min()
    )

    # Bollinger / mean reversion
    x["bb_mid"] = (
        x["close"].rolling(20).mean()
    )

    x["bb_std"] = (
        x["close"].rolling(20).std()
    )

    x["bb_z"] = (
        (x["close"] - x["bb_mid"])
        / x["bb_std"].replace(0, np.nan)
    )

    x["bb_width"] = (
        4 * x["bb_std"]
        / x["bb_mid"].replace(0, np.nan)
    )

    # Trend slope
    x["ema20_slope"] = (
        x["ema20"].pct_change(5) * 100
    )

    x["ema50_slope"] = (
        x["ema50"].pct_change(10) * 100
    )

    # Momentum acceleration
    x["momentum_accel"] = (
        x["ret3"] - x["ret12"] / 4
    )

    # Stochastic
    lowest = x["low"].rolling(14).min()
    highest = x["high"].rolling(14).max()

    x["stoch_k"] = (
        100
        * (x["close"] - lowest)
        / (highest - lowest).replace(
            0,
            np.nan,
        )
    )

    x["stoch_d"] = (
        x["stoch_k"].rolling(3).mean()
    )

    # ATR percentile
    x["atr_rank"] = (
        x["atr_pct"]
        .rolling(100)
        .rank(pct=True)
    )

    # Candle expansion
    x["range_pct"] = (
        (x["high"] - x["low"])
        / x["close"]
        * 100
    )

    x["range_ratio"] = (
        x["range_pct"]
        / x["range_pct"]
        .rolling(20)
        .mean()
        .replace(0, np.nan)
    )

    # Volume breakout
    x["volume_breakout"] = (
        x["volume"]
        / x["volume"]
        .rolling(55)
        .max()
        .replace(0, np.nan)
    )

    return x


# ============================================================
# MULTI-TIMEFRAME
# ============================================================

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

    d1h = indicators(
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

    def prepare_htf(data, suffix):

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
                "volume_ratio",
            ]
        ].copy()

        # Only data from completed HTF candles.
        z["available"] = z["time"].shift(-1)

        z = z.dropna(
            subset=["available"]
        )

        rename = {
            "close": f"close_{suffix}",
            "ema20": f"ema20_{suffix}",
            "ema50": f"ema50_{suffix}",
            "ema200": f"ema200_{suffix}",
            "rsi": f"rsi_{suffix}",
            "macd_hist": f"macd_{suffix}",
            "adx": f"adx_{suffix}",
            "atr_pct": f"atrpct_{suffix}",
            "volume_ratio": f"volume_{suffix}",
        }

        return (
            z.rename(columns=rename)
            .drop(columns=["time"])
        )

    out = pd.merge_asof(
        d5.sort_values("time"),
        prepare_htf(d15, "15m")
        .sort_values("available"),
        left_on="time",
        right_on="available",
        direction="backward",
    )

    out = pd.merge_asof(
        out.sort_values("time"),
        prepare_htf(d1h, "1h")
        .sort_values("available"),
        left_on="time",
        right_on="available",
        direction="backward",
    )

    required = [
        "atr",
        "adx",
        "ema20_15m",
        "ema50_15m",
        "ema200_15m",
        "ema20_1h",
        "ema50_1h",
        "ema200_1h",
        "rsi_15m",
        "rsi_1h",
        "adx_15m",
        "adx_1h",
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
# STRATEGY SIGNALS
# ============================================================

def make_signals(data, p):

    x = data

    family = p.get(
        "family",
        "trend",
    )

    adx_ok = (
        (x["adx"] >= p.get("adx_min", 18))
        &
        (
            x["adx_1h"]
            >= p.get("adx_htf", 18)
        )
    )

    volume_ok = (
        x["volume_ratio"]
        >= p.get("volume_min", 1.0)
    )

    volatility_ok = x[
        "vol_regime"
    ].between(
        p.get("vol_min", 0.55),
        p.get("vol_max", 2.8),
    )

    # --------------------------------------------------------
    # TREND
    # --------------------------------------------------------

    if family == "trend":

        long_core = (
            (x["ema20_1h"] > x["ema50_1h"])
            &
            (x["ema50_1h"] > x["ema200_1h"])
            &
            (x["ema20_15m"] > x["ema50_15m"])
            &
            (
                x["ema20_slope"]
                > p.get("slope_min", 0.02)
            )
            &
            x["rsi"].between(
                p["rsi_min"],
                p["rsi_max"],
            )
            &
            (x["macd_hist"] > 0)
            &
            (x["ret3"] > 0)
        )

        short_core = (
            (x["ema20_1h"] < x["ema50_1h"])
            &
            (x["ema50_1h"] < x["ema200_1h"])
            &
            (x["ema20_15m"] < x["ema50_15m"])
            &
            (
                x["ema20_slope"]
                < -p.get("slope_min", 0.02)
            )
            &
            x["rsi"].between(
                100 - p["rsi_max"],
                100 - p["rsi_min"],
            )
            &
            (x["macd_hist"] < 0)
            &
            (x["ret3"] < 0)
        )

        long_score = (
            long_core.astype(int) * 55
            + adx_ok.astype(int) * 20
            + volume_ok.astype(int) * 10
            + volatility_ok.astype(int) * 15
        )

        short_score = (
            short_core.astype(int) * 55
            + adx_ok.astype(int) * 20
            + volume_ok.astype(int) * 10
            + volatility_ok.astype(int) * 15
        )

    # --------------------------------------------------------
    # BREAKOUT
    # --------------------------------------------------------

    elif family == "breakout":

        long_core = (
            (x["close"] > x["high55"])
            &
            (x["ema20_15m"] > x["ema50_15m"])
            &
            (
                x["rsi"]
                > p.get("rsi_break_long", 55)
            )
        )

        short_core = (
            (x["close"] < x["low55"])
            &
            (x["ema20_15m"] < x["ema50_15m"])
            &
            (
                x["rsi"]
                < p.get("rsi_break_short", 45)
            )
        )

        expansion = (
            x["range_ratio"]
            >= p.get("range_ratio", 1.15)
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

    # --------------------------------------------------------
    # PULLBACK
    # --------------------------------------------------------

    elif family == "pullback":

        pullback = p.get(
            "pullback_pct",
            0.005,
        )

        long_core = (
            (x["ema20_1h"] > x["ema50_1h"])
            &
            (x["ema50_1h"] > x["ema200_1h"])
            &
            (
                x["close"]
                <= x["ema20"] * (1 + pullback)
            )
            &
            (x["close"] >= x["ema50"])
            &
            x["rsi"].between(
                p.get("rsi_long_min", 45),
                p.get("rsi_long_max", 58),
            )
            &
            (
                x["macd_hist"]
                > x["macd_hist"].shift(1)
            )
        )

        short_core = (
            (x["ema20_1h"] < x["ema50_1h"])
            &
            (x["ema50_1h"] < x["ema200_1h"])
            &
            (
                x["close"]
                >= x["ema20"] * (1 - pullback)
            )
            &
            (x["close"] <= x["ema50"])
            &
            x["rsi"].between(
                p.get("rsi_short_min", 42),
                p.get("rsi_short_max", 55),
            )
            &
            (
                x["macd_hist"]
                < x["macd_hist"].shift(1)
            )
        )

        long_score = (
            long_core.astype(int) * 65
            + adx_ok.astype(int) * 20
            + volume_ok.astype(int) * 5
            + volatility_ok.astype(int) * 10
        )

        short_score = (
            short_core.astype(int) * 65
            + adx_ok.astype(int) * 20
            + volume_ok.astype(int) * 5
            + volatility_ok.astype(int) * 10
        )

    # --------------------------------------------------------
    # MEAN REVERSION
    # --------------------------------------------------------

    elif family == "mean_reversion":

        long_core = (
            (x["bb_z"] <= -p.get("z_entry", 1.6))
            &
            (
                x["rsi"]
                <= p.get("rsi_oversold", 32)
            )
            &
            (
                x["stoch_k"]
                < p.get("stoch_long", 25)
            )
            &
            (x["close"] > x["close"].shift(1))
        )

        short_core = (
            (x["bb_z"] >= p.get("z_entry", 1.6))
            &
            (
                x["rsi"]
                >= 100 - p.get(
                    "rsi_oversold",
                    32,
                )
            )
            &
            (
                x["stoch_k"]
                > 100 - p.get(
                    "stoch_long",
                    25,
                )
            )
            &
            (x["close"] < x["close"].shift(1))
        )

        range_regime = (
            x["adx"]
            <= p.get("adx_max", 24)
        ) & volatility_ok

        long_score = (
            long_core.astype(int) * 70
            + range_regime.astype(int) * 20
            + (
                x["volume_ratio"]
                >= p.get("volume_min", 0.8)
            ).astype(int) * 10
        )

        short_score = (
            short_core.astype(int) * 70
            + range_regime.astype(int) * 20
            + (
                x["volume_ratio"]
                >= p.get("volume_min", 0.8)
            ).astype(int) * 10
        )

    # --------------------------------------------------------
    # MOMENTUM
    # --------------------------------------------------------

    elif family == "momentum":

        long_core = (
            (
                x["ret3"]
                > p.get("ret3_min", 0.004)
            )
            &
            (
                x["ret12"]
                > p.get("ret12_min", 0.008)
            )
            &
            (x["macd_hist"] > 0)
            &
            (
                x["rsi"]
                > p.get("rsi_momentum", 55)
            )
        )

        short_core = (
            (
                x["ret3"]
                < -p.get("ret3_min", 0.004)
            )
            &
            (
                x["ret12"]
                < -p.get("ret12_min", 0.008)
            )
            &
            (x["macd_hist"] < 0)
            &
            (
                x["rsi"]
                < 100 - p.get(
                    "rsi_momentum",
                    55,
                )
            )
        )

        expansion = (
            (
                x["range_ratio"]
                >= p.get("range_ratio", 1.05)
            )
            &
            (
                x["atr_rank"]
                >= p.get("atr_rank", 0.55)
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
# METRICS
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

    if len(equity) == 0:
        return {
            "return": 0.0,
            "pf": 0.0,
            "wr": 0.0,
            "dd": 0.0,
            "trades": 0,
            "expectancy": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_loss_streak": 0,
        }

    gross_profit = (
        p[p > 0].sum()
        if len(p)
        else 0.0
    )

    gross_loss = abs(
        p[p < 0].sum()
    ) if len(p) else 0.0

    if gross_loss > 0:
        profit_factor = (
            gross_profit
            / gross_loss
        )
    elif gross_profit > 0:
        profit_factor = np.inf
    else:
        profit_factor = 0.0

    win_rate = (
        (p > 0).mean() * 100
        if len(p)
        else 0.0
    )

    total_return = (
        equity[-1] / capital - 1
    ) * 100

    peaks = np.maximum.accumulate(
        equity
    )

    drawdowns = (
        equity / peaks - 1
    ) * 100

    max_drawdown = (
        float(drawdowns.min())
        if len(drawdowns)
        else 0.0
    )

    expectancy = (
        float(np.mean(p))
        if len(p)
        else 0.0
    )

    if len(p) > 1:
        std = float(
            np.std(
                p,
                ddof=1,
            )
        )

        if std > 0:
            sharpe = float(
                np.mean(p)
                / std
                * np.sqrt(len(p))
            )
        else:
            sharpe = 0.0
    else:
        sharpe = 0.0

    negative = p[p < 0]

    if len(negative) > 1:
        downside_std = float(
            np.std(
                negative,
                ddof=1,
            )
        )

        if downside_std > 0:
            sortino = float(
                np.mean(p)
                / downside_std
                * np.sqrt(len(p))
            )
        else:
            sortino = 0.0
    else:
        sortino = 0.0

    max_loss_streak = 0
    current_streak = 0

    for value in p:

        if value < 0:
            current_streak += 1
            max_loss_streak = max(
                max_loss_streak,
                current_streak,
            )
        else:
            current_streak = 0

    return {
        "return": float(total_return),
        "pf": float(profit_factor),
        "wr": float(win_rate),
        "dd": float(max_drawdown),
        "trades": int(len(p)),
        "expectancy": expectancy,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_loss_streak": int(
            max_loss_streak
        ),
    }


# ============================================================
# BACKTEST ENGINE
# ============================================================

def run_backtest(
    data,
    params,
    mode,
    capital,
    risk,
    fee,
    slip,
    direction=None,
    return_pnls=False,
):

    open_prices = data["open"].to_numpy(
        dtype=float
    )

    close_prices = data["close"].to_numpy(
        dtype=float
    )

    highs = data["high"].to_numpy(
        dtype=float
    )

    lows = data["low"].to_numpy(
        dtype=float
    )

    atr = data["atr"].to_numpy(
        dtype=float
    )

    long_score, short_score = make_signals(
        data,
        params,
    )

    threshold = int(
        params["threshold"]
    )

    if mode == "Agressief":
        threshold -= 5

    min_edge = int(
        params.get(
            "min_edge",
            5,
        )
    )

    long_signal = (
        (long_score >= threshold)
        &
        (
            long_score
            > short_score + min_edge
        )
    )

    short_signal = (
        (short_score >= threshold)
        &
        (
            short_score
            > long_score + min_edge
        )
    )

    if direction == "LONG":
        signal = long_signal

    elif direction == "SHORT":
        signal = short_signal

    else:
        signal = None

    cash = float(capital)

    position = 0

    entry = 0.0
    stop = 0.0
    take_profit = 0.0
    quantity = 0.0

    age = 0

    initial_risk_distance = 0.0
    best_price = 0.0

    pnls = []

    equity = np.empty(
        len(data),
        dtype=float,
    )

    equity[0] = cash

    for i in range(1, len(data)):

        exited = False

        # ====================================================
        # MANAGE EXISTING POSITION
        # ====================================================

        if position != 0:

            age += 1

            exit_price = None

            # ------------------------------------------------
            # LONG
            # ------------------------------------------------

            if position == 1:

                best_price = max(
                    best_price,
                    highs[i],
                )

                trail_trigger = (
                    initial_risk_distance
                    * params.get(
                        "trail_trigger_r",
                        1.0,
                    )
                )

                if (
                    best_price - entry
                    >= trail_trigger
                ):

                    trailing_stop = (
                        best_price
                        - atr[i]
                        * params.get(
                            "trail_atr",
                            1.0,
                        )
                    )

                    stop = max(
                        stop,
                        trailing_stop,
                    )

                if lows[i] <= stop:
                    exit_price = stop

                elif highs[i] >= take_profit:
                    exit_price = take_profit

            # ------------------------------------------------
            # SHORT
            # ------------------------------------------------

            else:

                best_price = min(
                    best_price,
                    lows[i],
                )

                trail_trigger = (
                    initial_risk_distance
                    * params.get(
                        "trail_trigger_r",
                        1.0,
                    )
                )

                if (
                    entry - best_price
                    >= trail_trigger
                ):

                    trailing_stop = (
                        best_price
                        + atr[i]
                        * params.get(
                            "trail_atr",
                            1.0,
                        )
                    )

                    stop = min(
                        stop,
                        trailing_stop,
                    )

                if highs[i] >= stop:
                    exit_price = stop

                elif lows[i] <= take_profit:
                    exit_price = take_profit

            # ------------------------------------------------
            # TIME EXIT
            # ------------------------------------------------

            if (
                exit_price is None
                and age
                >= params["max_bars"]
            ):
                exit_price = close_prices[i]

            # ------------------------------------------------
            # EXECUTE EXIT
            # ------------------------------------------------

            if exit_price is not None:

                if position == 1:

                    execution_exit = (
                        exit_price
                        * (
                            1
                            - slip / 100
                        )
                    )

                    gross = (
                        execution_exit
                        - entry
                    ) * quantity

                else:

                    execution_exit = (
                        exit_price
                        * (
                            1
                            + slip / 100
                        )
                    )

                    gross = (
                        entry
                        - execution_exit
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

        # ====================================================
        # NEW POSITION
        # ====================================================

        if (
            position == 0
            and not exited
            and cash > 0
            and i + 1 < len(data)
        ):

            if direction is None:

                if long_signal[i - 1]:
                    side = 1

                elif short_signal[i - 1]:
                    side = -1

                else:
                    side = 0

            else:

                side = (
                    1
                    if signal[i - 1]
                    else 0
                )

                if direction == "SHORT":
                    side = (
                        -1
                        if signal[i - 1]
                        else 0
                    )

            if (
                side != 0
                and np.isfinite(
                    atr[i - 1]
                )
                and atr[i - 1] > 0
            ):

                distance = max(
                    atr[i - 1]
                    * params["sl_atr"],
                    close_prices[i - 1]
                    * params["min_stop_pct"]
                    / 100,
                )

                quantity = (
                    cash
                    * risk
                    / 100
                    / distance
                )

                # --------------------------------------------
                # LONG ENTRY
                # --------------------------------------------

                if side == 1:

                    entry = (
                        open_prices[i]
                        * (
                            1
                            + slip / 100
                        )
                    )

                    stop = (
                        entry
                        - distance
                    )

                    take_profit = (
                        entry
                        + distance
                        * params["rr"]
                    )

                    best_price = entry

                # --------------------------------------------
                # SHORT ENTRY
                # --------------------------------------------

                else:

                    entry = (
                        open_prices[i]
                        * (
                            1
                            - slip / 100
                        )
                    )

                    stop = (
                        entry
                        + distance
                    )

                    take_profit = (
                        entry
                        - distance
                        * params["rr"]
                    )

                    best_price = entry

                initial_risk_distance = distance

                position = side

                age = 0

        # ====================================================
        # EQUITY
        # ====================================================

        equity[i] = cash

    metrics = calculate_metrics(
        pnls,
        equity,
        capital,
    )

    if return_pnls:
        metrics["pnls"] = np.asarray(
            pnls,
            dtype=float,
        )

    return metrics


def backtest(
    data,
    params,
    mode,
    capital,
    risk,
    fee,
    slip,
):
    return run_backtest(
        data,
        params,
        mode,
        capital,
        risk,
        fee,
        slip,
    )


def backtest_direction(
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
    return run_backtest(
        data,
        params,
        mode,
        capital,
        risk,
        fee,
        slip,
        direction=direction,
        return_pnls=return_pnls,
    )


# ============================================================
# MONTE CARLO
# ============================================================

def monte_carlo_stats(
    pnls,
    capital,
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

    rng = np.random.default_rng(
        seed
    )

    returns = np.empty(
        simulations
    )

    drawdowns = np.empty(
        simulations
    )

    for j in range(simulations):

        sample = rng.choice(
            p,
            size=len(p),
            replace=True,
        )

        equity = capital + np.cumsum(
            sample
        )

        curve = np.r_[
            capital,
            equity,
        ]

        peaks = np.maximum.accumulate(
            curve
        )

        dd = (
            curve / peaks - 1
        ) * 100

        returns[j] = (
            equity[-1] / capital - 1
        ) * 100

        drawdowns[j] = dd.min()

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
# STRATEGY GRID
# ============================================================

STRATEGIES = []


# ------------------------------------------------------------
# TREND
# ------------------------------------------------------------

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
                    "volume_min": 1.0,
                    "vol_min": 0.55,
                    "vol_max": 2.8,
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


# ------------------------------------------------------------
# BREAKOUT
# ------------------------------------------------------------

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

        for range_ratio in [
            1.10,
            1.25,
            1.40,
        ]:

            STRATEGIES.append(
                {
                    "family": "breakout",
                    "adx_min": 18,
                    "adx_htf": 18,
                    "volume_min": 1.0,
                    "vol_min": 0.55,
                    "vol_max": 3.0,
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


# ------------------------------------------------------------
# PULLBACK
# ------------------------------------------------------------

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

        for pullback_pct in [
            0.003,
            0.005,
            0.008,
        ]:

            STRATEGIES.append(
                {
                    "family": "pullback",
                    "adx_min": 18,
                    "adx_htf": 18,
                    "volume_min": 0.8,
                    "vol_min": 0.45,
                    "vol_max": 2.5,
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


# ------------------------------------------------------------
# MEAN REVERSION
# ------------------------------------------------------------

for sl_atr, rr in [
    (1.25, 1.5),
    (1.5, 2.0),
]:

    for threshold in [
        60,
        70,
    ]:

        for z_entry in [
            1.5,
            1.8,
            2.1,
        ]:

            STRATEGIES.append(
                {
                    "family": "mean_reversion",
                    "adx_min": 0,
                    "adx_htf": 0,
                    "adx_max": 24,
                    "volume_min": 0.8,
                    "vol_min": 0.45,
                    "vol_max": 1.5,
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
                }
            )


# ------------------------------------------------------------
# MOMENTUM
# ------------------------------------------------------------

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

        for momentum in [
            0.003,
            0.005,
            0.008,
        ]:

            STRATEGIES.append(
                {
                    "family": "momentum",
                    "adx_min": 18,
                    "adx_htf": 18,
                    "volume_min": 1.0,
                    "vol_min": 0.55,
                    "vol_max": 3.0,
                    "ret3_min": momentum,
                    "ret12_min": momentum * 2,
                    "rsi_momentum": 55,
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
# STABILITY
# ============================================================

def strategy_stability(
    data,
    params,
    mode,
    capital,
    risk,
    fee,
    slip,
    direction,
):

    family = params["family"]

    peers = [
        candidate
        for candidate in STRATEGIES
        if candidate["family"] == family
    ]

    if not peers:
        return 0.0

    results = []

    n = len(data)

    validation_ranges = [
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

    # Test only a representative neighborhood
    # to keep the application reasonably fast.
    for candidate in peers:

        folds = []

        for start, end in validation_ranges:

            validation = (
                data.iloc[start:end]
                .reset_index(drop=True)
            )

            result = backtest_direction(
                validation,
                candidate,
                mode,
                capital,
                risk,
                fee,
                slip,
                direction,
            )

            folds.append(result)

        positive = sum(
            result["return"] > 0
            for result in folds
        )

        profitable = sum(
            result["pf"] >= 1.0
            for result in folds
        )

        trades = sum(
            result["trades"]
            for result in folds
        )

        good = (
            positive >= 2
            and profitable >= 2
            and trades >= 15
        )

        results.append(
            bool(good)
        )

    return float(
        np.mean(results)
    ) if results else 0.0


# ============================================================
# CANDIDATE STATUS
# ============================================================

def candidate_status(
    folds,
    oos,
    monte_carlo,
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
            monte_carlo["p05_return"]
        )
        and monte_carlo["p05_return"] > -10
    )

    stability_ok = (
        stability >= 0.60
    )

    confidence = (
        min(wf_good / 3, 1)
        * 25
        +
        min(
            max(oos["pf"] - 1, 0),
            1,
        )
        * 25
        +
        min(
            max(oos["return"], 0)
            / 20,
            1,
        )
        * 15
        +
        min(
            max(oos["dd"] + 20, 0)
            / 20,
            1,
        )
        * 10
        +
        min(
            max(
                monte_carlo[
                    "p05_return"
                ],
                0,
            )
            / 10,
            1,
        )
        * 10
        +
        stability
        * 15
    )

    confidence = round(
        confidence,
        1,
    )

    if (
        wf_good >= 2
        and hard_oos
        and mc_ok
        and stability_ok
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

    if not stability_ok:
        reasons.append(
            f"stability {stability:.0%} < 60%"
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


# ============================================================
# STRATEGY DISCOVERY
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

    limit = int(
        days
        * 24
        * 12
    )

    data = build_mtf(
        symbol,
        limit,
    )

    if len(data) < 500:

        return {
            "Coin": symbol,
            "Status": "NO DATA",
            "Reason": (
                f"Te weinig data ({len(data)})"
            ),
        }

    n = len(data)

    final_start = int(
        n * 0.80
    )

    final_oos = (
        data.iloc[final_start:]
        .reset_index(drop=True)
    )

    candidates = []

    validation_ranges = [
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

    # ========================================================
    # DISCOVERY
    # ========================================================

    for base_params in STRATEGIES:

        for direction in [
            "LONG",
            "SHORT",
        ]:

            params = dict(
                base_params
            )

            folds = []

            for start, end in validation_ranges:

                validation = (
                    data.iloc[start:end]
                    .reset_index(drop=True)
                )

                result = backtest_direction(
                    validation,
                    params,
                    mode,
                    capital,
                    risk,
                    fee,
                    slip,
                    direction,
                )

                folds.append(
                    result
                )

            wf_good = sum(
                result["return"] > 0
                and result["pf"] >= 1.05
                for result in folds
            )

            average_pf = np.mean(
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

            average_return = np.mean(
                [
                    result["return"]
                    for result in folds
                ]
            )

            total_trades = sum(
                result["trades"]
                for result in folds
            )

            if total_trades < 15:
                continue

            discovery_score = (
                wf_good / 3 * 40
                +
                min(
                    average_pf / 1.5,
                    1,
                ) * 25
                +
                min(
                    max(
                        average_return,
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
                    params,
                    direction,
                    folds,
                )
            )

    if not candidates:

        return {
            "Coin": symbol,
            "Status": "NO EDGE",
            "Reason": (
                "Geen strategie haalde "
                "de minimale activiteit."
            ),
        }

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    # Only investigate the strongest candidates.
    finalists = candidates[:15]

    best = None

    # ========================================================
    # OOS + STABILITY + MONTE CARLO
    # ========================================================

    for (
        discovery_score,
        params,
        direction,
        folds,
    ) in finalists:

        stability = strategy_stability(
            data,
            params,
            mode,
            capital,
            risk,
            fee,
            slip,
            direction,
        )

        oos = backtest_direction(
            final_oos,
            params,
            mode,
            capital,
            risk,
            fee,
            slip,
            direction,
            return_pnls=True,
        )

        monte_carlo = monte_carlo_stats(
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
                monte_carlo,
                stability,
            )
        )

        ranking = (
            1 if status == "TRADE"
            else 0,
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

        item = (
            ranking,
            discovery_score,
            params,
            direction,
            folds,
            oos,
            monte_carlo,
            status,
            confidence,
            reason,
            stability,
        )

        if (
            best is None
            or ranking > best[0]
        ):
            best = item

    (
        _ranking,
        discovery_score,
        params,
        direction,
        folds,
        oos,
        monte_carlo,
        status,
        confidence,
        reason,
        stability,
    ) = best

    # ========================================================
    # OPPOSITE DIRECTION
    # ========================================================

    opposite = (
        "SHORT"
        if direction == "LONG"
        else "LONG"
    )

    opposite_oos = backtest_direction(
        final_oos,
        params,
        mode,
        capital,
        risk,
        fee,
        slip,
        opposite,
    )

    # ========================================================
    # RESULT
    # ========================================================

    return {
        "Coin": symbol,
        "Status": status,
        "Strategy": params["family"].upper(),
        "Direction": direction,
        "Confidence": confidence,
        "Stability": round(
            stability * 100,
            1,
        ),
        "Discovery": round(
            float(discovery_score),
            1,
        ),
        "WF": (
            f"{sum("
            "result['return'] > 0 "
            "and result['pf'] >= 1.05 "
            "for result in folds"
            ")}/3"
        ),
        "OOS PF": round(
            oos["pf"],
            3,
        ),
        "OOS %": round(
            oos["return"],
            2,
        ),
        "OOS trades": oos[
            "trades"
        ],
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
                monte_carlo[
                    "p05_return"
                ],
                2,
            )
            if np.isfinite(
                monte_carlo[
                    "p05_return"
                ]
            )
            else np.nan
        ),
        "MC median %": (
            round(
                monte_carlo[
                    "median_return"
                ],
                2,
            )
            if np.isfinite(
                monte_carlo[
                    "median_return"
                ]
            )
            else np.nan
        ),
        "MC P95 DD": (
            round(
                monte_carlo[
                    "p95_dd"
                ],
                2,
            )
            if np.isfinite(
                monte_carlo[
                    "p95_dd"
                ]
            )
            else np.nan
        ),
        "Reason": reason,
        "SL ATR": params[
            "sl_atr"
        ],
        "RR": params[
            "rr"
        ],
        "threshold": params[
            "threshold"
        ],
        "max bars": params[
            "max_bars"
        ],
    }


# ============================================================
# OPTIMIZER
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

    result = strategy_discovery(
        symbol,
        days,
        mode,
        capital,
        risk,
        fee,
        slip,
    )

    status = result.get(
        "Status"
    )

    if status in {
        "NO DATA",
        "NO EDGE",
        "ERROR",
    }:

        return {
            "Coin": symbol,
            "Status": "AFGEKEURD",
            "Reason": result.get(
                "Reason",
                "Geen edge",
            ),
        }

    return {
        "Coin": symbol,
        "Status": (
            "ROBUST"
            if status == "TRADE"
            else "AFGEKEURD"
        ),
        "Robustness": result.get(
            "Confidence",
            0,
        ),
        "Strategy": result.get(
            "Strategy"
        ),
        "Direction": result.get(
            "Direction"
        ),
        "Stability": result.get(
            "Stability"
        ),
        "WF consistency": result.get(
            "WF"
        ),
        "OOS PF": result.get(
            "OOS PF"
        ),
        "OOS %": result.get(
            "OOS %"
        ),
        "OOS trades": result.get(
            "OOS trades"
        ),
        "OOS WR": result.get(
            "OOS WR"
        ),
        "OOS DD": result.get(
            "OOS DD"
        ),
        "Expectancy": result.get(
            "Expectancy"
        ),
        "Sharpe": result.get(
            "Sharpe"
        ),
        "Sortino": result.get(
            "Sortino"
        ),
        "Max loss streak": result.get(
            "Max loss streak"
        ),
        "MC P05 %": result.get(
            "MC P05 %"
        ),
        "Reason": result.get(
            "Reason"
        ),
        "SL ATR": result.get(
            "SL ATR"
        ),
        "RR": result.get(
            "RR"
        ),
        "threshold": result.get(
            "threshold"
        ),
        "max bars": result.get(
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
    "Trend • Breakout • Pullback • Mean-Reversion • "
    "Momentum • LONG/SHORT • Walk-forward • "
    "Monte Carlo • Stability • OOS"
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("⚙️ Instellingen")

    mode = st.radio(
        "Strategie-modus",
        [
            "Conservatief",
            "Agressief",
        ],
    )

    capital = st.number_input(
        "Startkapitaal (€)",
        min_value=100.0,
        max_value=100000.0,
        value=1000.0,
        step=100.0,
    )

    risk = st.slider(
        "Risico per trade (%)",
        min_value=0.25,
        max_value=2.0,
        value=1.0,
        step=0.25,
    )

    fee = st.number_input(
        "Fee per kant (%)",
        min_value=0.0,
        max_value=0.50,
        value=0.10,
        step=0.01,
    )

    slip = st.number_input(
        "Slippage per kant (%)",
        min_value=0.0,
        max_value=0.50,
        value=0.03,
        step=0.01,
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

    st.divider()

    st.caption(
        f"Engine: v{APP_VERSION}"
    )

    st.caption(
        f"{len(STRATEGIES)} strategie-varianten"
    )


# ============================================================
# CONFIG
# ============================================================

current_config = make_config(
    days,
    mode,
    capital,
    risk,
    fee,
    slip,
)

store = load_store()

if store["config"] != current_config:
    active_results = {}
else:
    active_results = store[
        "results"
    ]


# ============================================================
# TABS
# ============================================================

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "🔬 Optimizer",
        "🧠 Strategy Discovery",
        "🏆 Robustness",
        "📈 Scanner",
    ]
)


# ============================================================
# TAB 1 — OPTIMIZER
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
        f"{done}/{len(COINS)} coins opgeslagen"
    )

    col1, col2 = st.columns(2)

    with col1:

        start = st.button(
            "🚀 Start / hervat optimizer",
            type="primary",
            use_container_width=True,
        )

    with col2:

        reset = st.button(
            "🧹 Nieuwe optimalisatie",
            use_container_width=True,
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
                f"⚙️ {symbol}: "
                f"strategy discovery + "
                f"robustness ({i + 1}/{len(COINS)})..."
            )

            started = time.time()

            try:

                result = optimize_coin(
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
                    "row": result,
                    "saved_at": (
                        pd.Timestamp.utcnow()
                        .isoformat()
                    ),
                }

                # Save after every coin.
                save_store(store)

                elapsed = (
                    time.time()
                    - started
                )

                status_box.write(
                    f"✅ {symbol} klaar "
                    f"in {elapsed:.1f}s — "
                    f"opgeslagen"
                )

            except Exception as exc:

                result = {
                    "Coin": symbol,
                    "Status": "FOUT",
                    "Reason": str(exc),
                }

                store["results"][
                    symbol
                ] = {
                    "row": result,
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
                (i + 1)
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
            "Nog geen optimizer-resultaten. "
            "Klik op 'Start / hervat optimizer'."
        )


# ============================================================
# TAB 2 — STRATEGY DISCOVERY
# ============================================================

with tab2:

    st.subheader(
        "🧠 Strategy Discovery"
    )

    st.write(
        "Hier worden meerdere strategie-families "
        "en LONG/SHORT-richtingen onderzocht. "
        "De laatste 20% van de data blijft volledig "
        "onaangeraakt voor de finale OOS-test."
    )

    st.info(
        "TRADE vereist: ≥2/3 walk-forward, "
        "≥15 OOS-trades, OOS PF ≥1.20, "
        "positief OOS-rendement, DD > -20%, "
        "Monte Carlo P05 > -10% en ≥60% stability."
    )

    discovery_key = (
        f"discovery_v841_"
        f"{days}_"
        f"{mode}_"
        f"{capital}_"
        f"{risk}_"
        f"{fee}_"
        f"{slip}"
    )

    start_discovery = st.button(
        "🧠 Start Strategy Discovery",
        type="primary",
        use_container_width=True,
    )

    if start_discovery:

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

        display = discovery.copy()

        status_order = {
            "TRADE": 0,
            "WATCH": 1,
            "NO TRADE": 2,
            "NO EDGE": 3,
            "NO DATA": 4,
            "ERROR": 5,
        }

        if "Status" in display.columns:

            display["_status_order"] = (
                display["Status"]
                .map(status_order)
                .fillna(9)
            )

            sort_columns = [
                "_status_order"
            ]

            ascending = [True]

            if "Confidence" in display.columns:

                sort_columns.append(
                    "Confidence"
                )

                ascending.append(False)

            display = (
                display
                .sort_values(
                    sort_columns,
                    ascending=ascending,
                )
                .drop(
                    columns=[
                        "_status_order"
                    ]
                )
            )

        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
        )

        trade_count = int(
            (
                display["Status"]
                == "TRADE"
            ).sum()
            if "Status" in display.columns
            else 0
        )

        watch_count = int(
            (
                display["Status"]
                == "WATCH"
            ).sum()
            if "Status" in display.columns
            else 0
        )

        if trade_count:

            st.success(
                f"🟢 {trade_count} "
                f"kandidaat/kandidaten "
                f"halen de TRADE-drempel."
            )

        elif watch_count:

            st.warning(
                f"🟡 {watch_count} "
                f"kandidaat/kandidaten "
                f"zijn WATCH."
            )

        else:

            st.info(
                "🔴 Geen robuuste edge gevonden. "
                "Dat is een geldig onderzoeksresultaat."
            )


# ============================================================
# TAB 3 — ROBUSTNESS
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

        data = pd.DataFrame(
            rows
        )

        if "Status" in data.columns:

            robust = data[
                data["Status"]
                == "ROBUST"
            ].copy()

        else:

            robust = pd.DataFrame()

        if len(robust):

            if "Robustness" in robust.columns:

                robust = robust.sort_values(
                    "Robustness",
                    ascending=False,
                    na_position="last",
                )

            st.success(
                f"🟢 {len(robust)} coin(s) "
                f"hebben een robuuste kandidaat."
            )

            st.dataframe(
                robust,
                use_container_width=True,
                hide_index=True,
            )

        else:

            st.warning(
                "Geen robuuste strategie gevonden."
            )

        st.info(
            "De optimizer forceert bewust geen winnaar. "
            "Een strategie moet meerdere onafhankelijke "
            "filters doorstaan."
        )

    else:

        st.info(
            "Voer eerst de optimizer uit."
        )


# ============================================================
# TAB 4 — SCANNER
# ============================================================

with tab4:

    st.subheader(
        "📈 Research Scanner"
    )

    st.write(
        "De scanner gebruikt de gevonden strategie "
        "en controleert de actuele marktsituatie. "
        "Dit plaatst geen orders."
    )

    selected = st.multiselect(
        "Coins",
        COINS,
        default=COINS[:5],
    )

    scan_button = st.button(
        "🔎 Scan nu",
        type="primary",
        use_container_width=True,
    )

    if scan_button:

        scan_rows = []

        for symbol in selected:

            try:

                saved = (
                    active_results
                    .get(symbol, {})
                    .get("row", {})
                )

                family = str(
                    saved.get(
                        "Strategy",
                        "TREND",
                    )
                ).lower()

                direction = saved.get(
                    "Direction"
                )

                params = {
                    "family": family,

                    "rsi_min": 52,
                    "rsi_max": 68,

                    "adx_min": 18,
                    "adx_htf": 18,

                    "volume_min": 1.0,

                    "vol_min": 0.55,
                    "vol_max": 2.8,

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

                data = build_mtf(
                    symbol,
                    1500,
                )

                long_scores, short_scores = (
                    make_signals(
                        data,
                        params,
                    )
                )

                latest = data.iloc[-1]

                long_score = int(
                    long_scores[-1]
                )

                short_score = int(
                    short_scores[-1]
                )

                raw_signal = "WAIT"

                if (
                    long_score
                    >= params["threshold"]
                    and
                    long_score
                    > short_score
                    + params["min_edge"]
                ):

                    raw_signal = "LONG"

                elif (
                    short_score
                    >= params["threshold"]
                    and
                    short_score
                    > long_score
                    + params["min_edge"]
                ):

                    raw_signal = "SHORT"

                allowed = saved.get(
                    "Status"
                ) in {
                    "TRADE",
                    "WATCH",
                }

                if (
                    allowed
                    and raw_signal != "WAIT"
                    and (
                        not direction
                        or direction
                        == raw_signal
                    )
                ):

                    signal = raw_signal

                else:

                    signal = "WAIT"

                scan_rows.append(
                    {
                        "Coin": symbol,
                        "Signal": signal,
                        "Strategy": family.upper(),
                        "Direction": (
                            direction
                            or "-"
                        ),
                        "Long score": long_score,
                        "Short score": short_score,
                        "ADX": round(
                            float(
                                latest["adx"]
                            ),
                            1,
                        ),
                        "RSI": round(
                            float(
                                latest["rsi"]
                            ),
                            1,
                        ),
                        "Vol ratio": round(
                            float(
                                latest[
                                    "volume_ratio"
                                ]
                            ),
                            2,
                        ),
                        "ATR %": round(
                            float(
                                latest[
                                    "atr_pct"
                                ]
                            ),
                            2,
                        ),
                        "Price": round(
                            float(
                                latest[
                                    "close"
                                ]
                            ),
                            6,
                        ),
                    }
                )

            except Exception as exc:

                scan_rows.append(
                    {
                        "Coin": symbol,
                        "Signal": "ERROR",
                        "Strategy": "-",
                        "Direction": "-",
                        "Long score": 0,
                        "Short score": 0,
                        "Error": str(exc),
                    }
                )

        scan_table = pd.DataFrame(
            scan_rows
        )

        st.dataframe(
            scan_table,
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.warning(
    "⚠️ Onderzoekstool. Geen financieel advies "
    "en geen live orders. Een positieve backtest "
    "is geen garantie voor toekomstige resultaten."
)

st.caption(
    f"Crypto DayTrader v{APP_VERSION} • "
    f"{len(STRATEGIES)} strategy variants • "
    "Research only"
)