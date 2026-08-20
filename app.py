import json
import os
import time

import numpy as np
import pandas as pd
import requests
import streamlit as st

# ============================================================
# Crypto DayTrader v8.4.1
# Robust crypto strategy research engine
# - Trend / Breakout / Pullback / Mean Reversion / Momentum
# - LONG and SHORT independently evaluated
# - Multi-timeframe confirmation (5m / 15m / 1h)
# - Realistic next-open execution
# - ATR stop, take profit and trailing stop
# - 3-fold walk-forward validation
# - Final 20% untouched OOS test
# - Parameter stability test on validation data only
# - Bootstrap Monte Carlo using actual OOS trade P&Ls
# - Autosave after every coin
# - No live orders
# ============================================================

APP_VERSION = "8.4.1"
BINANCE = "https://data-api.binance.vision/api/v3/klines"

COINS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT", "DOTUSDT",
]

RESULTS_FILE = "optimizer_results_v841.json"

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
    }


# ============================================================
# Binance data
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

    true_range = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr_value = true_range.ewm(
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
        / atr_value.replace(0, np.nan)
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
        / atr_value.replace(0, np.nan)
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

    true_range = pd.concat(
        [
            x.high - x.low,
            (x.high - x.close.shift()).abs(),
            (x.low - x.close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)

    x["atr"] = true_range.ewm(
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

    x["high20"] = x.high.shift(1).rolling(20).max()
    x["low20"] = x.low.shift(1).rolling(20).min()

    x["high55"] = x.high.shift(1).rolling(55).max()
    x["low55"] = x.low.shift(1).rolling(55).min()

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
        (x.high - x.low) / x.close * 100
    )

    x["range_ratio"] = (
        x.range_pct
        / x.range_pct.rolling(20).mean().replace(0, np.nan)
    )

    x["vol_breakout"] = (
        x.volume
        / x.volume.rolling(55).max().replace(0, np.nan)
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
                max(500, limit // 3 + 100),
            ),
        )
    )

    d1 = indicators(
        fetch(
            symbol,
            "1h",
            min(
                5000,
                max(500, limit // 12 + 100),
            ),
        )
    )

    def higher_timeframe(data, suffix):
        columns = [
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

        z = data[columns].copy()

        # A higher-timeframe candle only becomes available
        # after that candle has closed.
        z["available"] = z.time.shift(-1)
        z = z.dropna(subset=["available"])

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

    output = pd.merge_asof(
        d5.sort_values("time"),
        higher_timeframe(
            d15,
            "15",
        ).sort_values("available"),
        left_on="time",
        right_on="available",
        direction="backward",
    )

    output = pd.merge_asof(
        output.sort_values("time"),
        higher_timeframe(
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
        if column not in output.columns
    ]

    if missing:
        raise KeyError(
            f"MTF-kolommen ontbreken: {missing}"
        )

    return (
        output
        .dropna(subset=required)
        .reset_index(drop=True)
    )


# ============================================================
# Strategy signals
# ============================================================

def make_signals(data, params):
    x = data
    family = params.get("family", "trend")

    adx_ok = (
        (x.adx >= params.get("adx_min", 18))
        & (x.adx1h >= params.get("adx_htf", 18))
    )

    volume_ok = (
        x.vol_ratio >= params.get("vol_min", 1.0)
    )

    volatility_ok = x.vol_regime.between(
        params.get("vol_regime_min", 0.55),
        params.get("vol_regime_max", 2.8),
    )

    if family == "trend":
        long_core = (
            (x.ema20_1h > x.ema50_1h)
            & (x.ema50_1h > x.ema200_1h)
            & (x.ema20_15 > x.ema50_15)
            & (
                x.ema20_slope
                > params.get("slope_min", 0.02)
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
                < -params.get("slope_min", 0.02)
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
            + volatility_ok.astype(int) * 15
        )

        short_score = (
            short_core.astype(int) * 55
            + adx_ok.astype(int) * 20
            + volume_ok.astype(int) * 10
            + volatility_ok.astype(int) * 15
        )

    elif family == "breakout":
        long_core = (
            (x.close > x.high55)
            & (x.ema20_15 > x.ema50_15)
            & (
                x.rsi
                > params.get("rsi_break_long", 55)
            )
        )

        short_core = (
            (x.close < x.low55)
            & (x.ema20_15 < x.ema50_15)
            & (
                x.rsi
                < params.get("rsi_break_short", 45)
            )
        )

        expansion = (
            x.range_ratio
            >= params.get("range_ratio", 1.15)
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
        pullback = params.get(
            "pullback_pct",
            0.005,
        )

        long_core = (
            (x.ema20_1h > x.ema50_1h)
            & (x.ema50_1h > x.ema200_1h)
            & (
                x.close
                <= x.ema20 * (1 + pullback)
            )
            & (x.close >= x.ema50)
            & x.rsi.between(
                params.get("rsi_long_min", 45),
                params.get("rsi_long_max", 58),
            )
            & (x.macd_hist > x.macd_hist.shift(1))
        )

        short_core = (
            (x.ema20_1h < x.ema50_1h)
            & (x.ema50_1h < x.ema200_1h)
            & (
                x.close
                >= x.ema20 * (1 - pullback)
            )
            & (x.close <= x.ema50)
            & x.rsi.between(
                params.get("rsi_short_min", 42),
                params.get("rsi_short_max", 55),
            )
            & (x.macd_hist < x.macd_hist.shift(1))
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

    elif family == "mean_reversion":
        z_entry = params.get(
            "z_entry",
            1.8,
        )

        oversold = params.get(
            "rsi_oversold",
            32,
        )

        stoch_long = params.get(
            "stoch_long",
            25,
        )

        long_core = (
            (x.bb_z <= -z_entry)
            & (x.rsi <= oversold)
            & (x.stoch_k < stoch_long)
            & (x.close > x.close.shift(1))
        )

        short_core = (
            (x.bb_z >= z_entry)
            & (x.rsi >= 100 - oversold)
            & (x.stoch_k > 100 - stoch_long)
            & (x.close < x.close.shift(1))
        )

        regime = (
            (x.adx <= params.get("adx_max", 24))
            & volatility_ok
        )

        volume_mean_reversion = (
            x.vol_ratio >= params.get(
                "vol_min",
                0.8,
            )
        )

        long_score = (
            long_core.astype(int) * 70
            + regime.astype(int) * 20
            + volume_mean_reversion.astype(int) * 10
        )

        short_score = (
            short_core.astype(int) * 70
            + regime.astype(int) * 20
            + volume_mean_reversion.astype(int) * 10
        )

    elif family == "momentum":
        ret3_min = params.get(
            "ret3_min",
            0.004,
        )

        ret12_min = params.get(
            "ret12_min",
            0.008,
        )

        long_core = (
            (x.ret3 > ret3_min)
            & (x.ret12 > ret12_min)
            & (x.macd_hist > 0)
            & (
                x.rsi
                > params.get("rsi_mom", 55)
            )
        )

        short_core = (
            (x.ret3 < -ret3_min)
            & (x.ret12 < -ret12_min)
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
# Backtest metrics
# ============================================================

def calculate_metrics(pnls, equity, capital):
    pnl_array = np.asarray(
        pnls,
        dtype=float,
    )

    wins = (
        pnl_array[pnl_array > 0].sum()
        if len(pnl_array)
        else 0.0
    )

    losses = (
        abs(pnl_array[pnl_array < 0].sum())
        if len(pnl_array)
        else 0.0
    )

    if losses:
        profit_factor = wins / losses
    elif wins:
        profit_factor = np.inf
    else:
        profit_factor = 0.0

    win_rate = (
        (pnl_array > 0).mean() * 100
        if len(pnl_array)
        else 0.0
    )

    final_equity = (
        equity[-1]
        if len(equity)
        else capital
    )

    return_pct = (
        final_equity / capital - 1
    ) * 100

    drawdown = (
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
        float(np.mean(pnl_array))
        if len(pnl_array)
        else 0.0
    )

    if len(pnl_array) > 1:
        std = float(
            np.std(
                pnl_array,
                ddof=1,
            )
        )
    else:
        std = 0.0

    sharpe = (
        float(
            np.mean(pnl_array)
            / std
            * np.sqrt(len(pnl_array))
        )
        if std > 0
        else 0.0
    )

    negative = pnl_array[pnl_array < 0]

    if len(negative) > 1:
        downside = float(
            np.std(
                negative,
                ddof=1,
            )
        )
    else:
        downside = 0.0

    sortino = (
        float(
            np.mean(pnl_array)
            / downside
            * np.sqrt(len(pnl_array))
        )
        if downside > 0
        else 0.0
    )

    current_streak = 0
    max_loss_streak = 0

    for value in pnl_array:
        if value < 0:
            current_streak += 1
            max_loss_streak = max(
                max_loss_streak,
                current_streak,
            )
        else:
            current_streak = 0

    return {
        "return": float(return_pct),
        "pf": float(profit_factor),
        "wr": float(win_rate),
        "dd": float(drawdown),
        "trades": int(len(pnl_array)),
        "expectancy": expectancy,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_loss_streak": int(max_loss_streak),
    }


# ============================================================
# Backtest engine
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
    opens = data.open.to_numpy(float)
    closes = data.close.to_numpy(float)
    highs = data.high.to_numpy(float)
    lows = data.low.to_numpy(float)
    atr_values = data.atr.to_numpy(float)

    long_score, short_score = make_signals(
        data,
        params,
    )

    threshold = params["threshold"]

    if mode == "Agressief":
        threshold -= 5

    if direction == "LONG":
        signals = (
            (long_score >= threshold)
            & (
                long_score
                > short_score + params["min_edge"]
            )
        )

    elif direction == "SHORT":
        signals = (
            (short_score >= threshold)
            & (
                short_score
                > long_score + params["min_edge"]
            )
        )

    else:
        signals_long = (
            (long_score >= threshold)
            & (
                long_score
                > short_score + params["min_edge"]
            )
        )

        signals_short = (
            (short_score >= threshold)
            & (
                short_score
                > long_score + params["min_edge"]
            )
        )

    cash = float(capital)

    position = 0
    entry = 0.0
    stop = 0.0
    take_profit = 0.0
    quantity = 0.0
    age = 0
    risk_distance = 0.0
    best_price = 0.0

    pnls = []

    equity = np.empty(
        len(data),
        dtype=float,
    )

    equity[0] = cash

    for i in range(1, len(data)):
        exited = False

        # -------------------------
        # Manage open position
        # -------------------------
        if position != 0:
            age += 1
            exit_price = None

            if position == 1:
                best_price = max(
                    best_price,
                    highs[i],
                )

                trigger = (
                    risk_distance
                    * params.get(
                        "trail_trigger_r",
                        1.0,
                    )
                )

                if (
                    best_price - entry
                    >= trigger
                ):
                    trail = (
                        best_price
                        - atr_values[i]
                        * params.get(
                            "trail_atr",
                            1.0,
                        )
                    )

                    stop = max(
                        stop,
                        trail,
                    )

                if lows[i] <= stop:
                    exit_price = stop

                elif highs[i] >= take_profit:
                    exit_price = take_profit

            else:
                best_price = min(
                    best_price,
                    lows[i],
                )

                trigger = (
                    risk_distance
                    * params.get(
                        "trail_trigger_r",
                        1.0,
                    )
                )

                if (
                    entry - best_price
                    >= trigger
                ):
                    trail = (
                        best_price
                        + atr_values[i]
                        * params.get(
                            "trail_atr",
                            1.0,
                        )
                    )

                    stop = min(
                        stop,
                        trail,
                    )

                if highs[i] >= stop:
                    exit_price = stop

                elif lows[i] <= take_profit:
                    exit_price = take_profit

            if (
                exit_price is None
                and age >= params["max_bars"]
            ):
                exit_price = closes[i]

            if exit_price is not None:
                if position == 1:
                    executed_exit = (
                        exit_price
                        * (1 - slip / 100)
                    )

                    gross = (
                        executed_exit - entry
                    ) * quantity

                else:
                    executed_exit = (
                        exit_price
                        * (1 + slip / 100)
                    )

                    gross = (
                        entry - executed_exit
                    ) * quantity

                fees = (
                    entry * quantity
                    + executed_exit * quantity
                ) * fee / 100

                pnl = gross - fees

                cash += pnl
                pnls.append(float(pnl))

                position = 0
                exited = True

        # -------------------------
        # New entry
        # -------------------------
        if (
            position == 0
            and not exited
            and cash > 0
            and i + 1 < len(data)
        ):
            if direction is None:
                if signals_long[i - 1]:
                    side = 1
                elif signals_short[i - 1]:
                    side = -1
                else:
                    side = 0

            else:
                side = (
                    1
                    if signals[i - 1]
                    else 0
                )

                if (
                    direction == "SHORT"
                    and signals[i - 1]
                ):
                    side = -1

            if (
                side
                and np.isfinite(
                    atr_values[i - 1]
                )
                and atr_values[i - 1] > 0
            ):
                distance = max(
                    atr_values[i - 1]
                    * params["sl_atr"],
                    closes[i - 1]
                    * params["min_stop_pct"]
                    / 100,
                )

                quantity = (
                    cash
                    * risk
                    / 100
                    / distance
                )

                if side == 1:
                    entry = (
                        opens[i]
                        * (1 + slip / 100)
                    )

                    stop = (
                        entry - distance
                    )

                    take_profit = (
                        entry
                        + distance
                        * params["rr"]
                    )

                else:
                    entry = (
                        opens[i]
                        * (1 - slip / 100)
                    )

                    stop = (
                        entry + distance
                    )

                    take_profit = (
                        entry
                        - distance
                        * params["rr"]
                    )

                risk_distance = distance
                best_price = entry
                position = side
                age = 0

        equity[i] = cash

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
        direction,
        return_pnls,
    )


# ============================================================
# Strategy grid
# ============================================================

STRATEGIES = []

# Trend
for sl_atr, rr in [
    (1.25, 1.5),
    (1.5, 2.0),
    (2.0, 2.5),
]:
    for threshold in [60, 70, 80]:
        for rsi_min, rsi_max in [
            (50, 65),
            (52, 68),
            (55, 70),
        ]:
            STRATEGIES.append({
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
            })

# Breakout
for sl_atr, rr in [
    (1.25, 1.5),
    (1.5, 2.0),
    (2.0, 2.5),
]:
    for threshold in [60, 70, 80]:
        for range_ratio in [
            1.10,
            1.25,
            1.40,
        ]:
            STRATEGIES.append({
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
            })

# Pullback
for sl_atr, rr in [
    (1.25, 1.5),
    (1.5, 2.0),
    (2.0, 2.5),
]:
    for threshold in [60, 70, 80]:
        for pullback_pct in [
            0.003,
            0.005,
            0.008,
        ]:
            STRATEGIES.append({
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
            })

# Mean reversion
for sl_atr, rr in [
    (1.25, 1.5),
    (1.5, 2.0),
]:
    for threshold in [60, 70]:
        for z_entry in [
            1.5,
            1.8,
            2.1,
        ]:
            STRATEGIES.append({
                "family": "mean_reversion",
                "adx_min": 0,
                "adx_htf": 0,
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
            })

# Momentum
for sl_atr, rr in [
    (1.25, 1.5),
    (1.5, 2.0),
    (2.0, 2.5),
]:
    for threshold in [60, 70, 80]:
        for momentum in [
            0.003,
            0.005,
            0.008,
        ]:
            STRATEGIES.append({
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
            })


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

    rng = np.random.default_rng(seed)

    returns = np.empty(
        simulations,
        dtype=float,
    )

    drawdowns = np.empty(
        simulations,
        dtype=float,
    )

    for index in range(simulations):
        sample = rng.choice(
            values,
            size=len(values),
            replace=True,
        )

        equity = capital + np.cumsum(sample)
        curve = np.r_[capital, equity]

        peak = np.maximum.accumulate(curve)

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

def strategy_stability(
    data,
    params,
    mode,
    capital,
    risk,
    fee,
    slip,
):
    family = params.get(
        "family",
        "trend",
    )

    direction = params.get(
        "direction",
        "LONG",
    )

    peers = [
        strategy
        for strategy in STRATEGIES
        if strategy.get("family") == family
    ]

    if not peers:
        return 0.0

    checks = []

    n = len(data)

    ranges = [
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

    # Limit the neighborhood to avoid excessive runtime.
    for peer in peers[:20]:
        peer_results = []

        for start, end in ranges:
            validation = (
                data.iloc[start:end]
                .reset_index(drop=True)
            )

            result = backtest_direction(
                validation,
                peer,
                mode,
                capital,
                risk,
                fee,
                slip,
                direction,
            )

            peer_results.append(result)

        average_pf = np.mean([
            min(result["pf"], 3)
            if np.isfinite(result["pf"])
            else 3
            for result in peer_results
        ])

        average_return = np.mean([
            result["return"]
            for result in peer_results
        ])

        trades = sum(
            result["trades"]
            for result in peer_results
        )

        stable = (
            average_return > 0
            and average_pf >= 1.0
            and trades >= 15
        )

        checks.append(stable)

    return (
        float(np.mean(checks))
        if checks
        else 0.0
    )


# ============================================================
# Candidate scoring
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

    stable_ok = stability >= 0.60

    confidence = round(
        min(wf_good / 3, 1) * 25
        + min(
            max(oos["pf"] - 1, 0),
            1,
        ) * 25
        + min(
            max(oos["return"], 0) / 20,
            1,
        ) * 15
        + min(
            max(oos["dd"] + 20, 0) / 20,
            1,
        ) * 10
        + min(
            max(
                monte_carlo["p05_return"],
                0,
            ) / 10,
            1,
        ) * 10
        + stability * 15,
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

    if not stable_ok:
        reasons.append(
            f"stability {stability:.0%} < 60%"
        )

    if not reasons:
        reason_text = "Alle hoofdcriteria gehaald"
    else:
        reason_text = "; ".join(reasons)

    return (
        status,
        confidence,
        reason_text,
    )


# ============================================================
# Strategy Discovery
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
            "Reason": (
                f"Te weinig bruikbare candles: "
                f"{len(data)}"
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

    for params in STRATEGIES:
        for direction in [
            "LONG",
            "SHORT",
        ]:
            candidate = dict(params)
            candidate["direction"] = direction

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

            wf_good = sum(
                result["return"] > 0
                and result["pf"] >= 1.05
                for result in folds
            )

            average_pf = np.mean([
                min(result["pf"], 3)
                if np.isfinite(result["pf"])
                else 3
                for result in folds
            ])

            average_return = np.mean([
                result["return"]
                for result in folds
            ])

            total_trades = sum(
                result["trades"]
                for result in folds
            )

            if total_trades < 15:
                continue

            discovery_score = (
                wf_good / 3 * 40
                + min(
                    average_pf / 1.5,
                    1,
                ) * 25
                + min(
                    max(average_return, 0)
                    / 15,
                    1,
                ) * 20
                + min(
                    total_trades / 45,
                    1,
                ) * 15
            )

            candidates.append(
                (
                    discovery_score,
                    candidate,
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
                "de minimumvoorwaarden."
            ),
        }

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    best = None

    for (
        discovery_score,
        params,
        direction,
        folds,
    ) in candidates[:12]:

        stability = strategy_stability(
            data,
            params,
            mode,
            capital,
            risk,
            fee,
            slip,
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

        safe_pf = (
            oos["pf"]
            if np.isfinite(oos["pf"])
            else 3
        )

        rank = (
            1 if status == "TRADE" else 0,
            confidence,
            stability,
            safe_pf,
            oos["return"],
        )

        candidate_result = (
            rank,
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
            or rank > best[0]
        ):
            best = candidate_result

    (
        _rank,
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

    wf_count = sum(
        result["return"] > 0
        and result["pf"] >= 1.05
        for result in folds
    )

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
        "Max loss streak": (
            oos["max_loss_streak"]
        ),
        "Opposite PF": round(
            opposite_oos["pf"],
            3,
        ),
        "MC P05 %": (
            round(
                monte_carlo["p05_return"],
                2,
            )
            if np.isfinite(
                monte_carlo["p05_return"]
            )
            else np.nan
        ),
        "MC median %": (
            round(
                monte_carlo["median_return"],
                2,
            )
            if np.isfinite(
                monte_carlo["median_return"]
            )
            else np.nan
        ),
        "MC P95 DD": (
            round(
                monte_carlo["p95_dd"],
                2,
            )
            if np.isfinite(
                monte_carlo["p95_dd"]
            )
            else np.nan
        ),
        "Reason": reason,
        "SL ATR": params["sl_atr"],
        "RR": params["rr"],
        "threshold": params["threshold"],
        "max bars": params["max_bars"],
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
        "Status",
        "ERROR",
    )

    if status in {
        "ERROR",
        "NO DATA",
        "NO EDGE",
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
            "Strategy",
        ),
        "Direction": result.get(
            "Direction",
        ),
        "Stability": result.get(
            "Stability",
        ),
        "WF consistency": result.get(
            "WF",
        ),
        "OOS PF": result.get(
            "OOS PF",
        ),
        "OOS %": result.get(
            "OOS %",
        ),
        "OOS trades": result.get(
            "OOS trades",
        ),
        "OOS WR": result.get(
            "OOS WR",
        ),
        "OOS DD": result.get(
            "OOS DD",
        ),
        "Expectancy": result.get(
            "Expectancy",
        ),
        "Sharpe": result.get(
            "Sharpe",
        ),
        "Sortino": result.get(
            "Sortino",
        ),
        "Max loss streak": result.get(
            "Max loss streak",
        ),
        "MC P05 %": result.get(
            "MC P05 %",
        ),
        "Reason": result.get(
            "Reason",
        ),
        "SL ATR": result.get(
            "SL ATR",
        ),
        "RR": result.get(
            "RR",
        ),
        "threshold": result.get(
            "threshold",
        ),
        "max bars": result.get(
            "max bars",
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
    "Momentum • LONG/SHORT • Walk-forward • OOS • "
    "Monte Carlo • Stability"
)


with st.sidebar:
    st.header("⚙️ Onderzoek")

    mode = st.radio(
        "Strategiemodus",
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
        "TRADE = strengste onderzoeksfilter."
    )
    st.caption(
        "Dit programma plaatst geen echte orders."
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
        "🔬 Robuuste optimizer"
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
        start_optimizer = st.button(
            "🚀 Start / hervat optimizer",
            type="primary",
        )

    with col2:
        reset_optimizer = st.button(
            "🧹 Nieuwe optimalisatie",
        )

    if reset_optimizer:
        new_store = {
            "config": current_config,
            "results": {},
        }

        save_store(new_store)
        st.rerun()

    if start_optimizer:
        working_store = {
            "config": current_config,
            "results": active_results,
        }

        progress = st.progress(
            done / len(COINS)
        )

        status_box = st.empty()

        for index, symbol in enumerate(COINS):
            if symbol in working_store["results"]:
                status_box.write(
                    f"✅ {symbol} al klaar — overslaan"
                )

                progress.progress(
                    (index + 1)
                    / len(COINS)
                )

                continue

            status_box.write(
                f"⚙️ {symbol}: analyse "
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
                )

                working_store["results"][
                    symbol
                ] = {
                    "row": row,
                    "saved_at": (
                        pd.Timestamp.utcnow()
                        .isoformat()
                    ),
                }

                save_store(
                    working_store
                )

                elapsed = (
                    time.time() - started
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

                working_store["results"][
                    symbol
                ] = {
                    "row": row,
                    "saved_at": (
                        pd.Timestamp.utcnow()
                        .isoformat()
                    ),
                }

                save_store(
                    working_store
                )

                status_box.error(
                    f"{symbol}: {exc}"
                )

            progress.progress(
                (index + 1)
                / len(COINS)
            )

        st.success(
            "Optimizer klaar."
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
            "Nog geen optimizerresultaten."
        )


# ============================================================
# Strategy Discovery
# ============================================================

with tab2:
    st.subheader(
        "🧠 Strategy Discovery"
    )

    st.write(
        "Deze analyse onderzoekt meerdere "
        "strategie-families per coin en richting. "
        "De laatste 20% van de data blijft "
        "onaangeroerde OOS-data."
    )

    st.info(
        "TRADE vereist: ≥2/3 WF, ≥15 OOS-trades, "
        "OOS PF ≥1.20, positief OOS-rendement, "
        "DD > -20%, MC P05 > -10% en "
        "≥60% parameter-stability."
    )

    discovery_key = (
        "discovery_v841_"
        f"{days}_{mode}_{capital}_{risk}_{fee}_{slip}"
    )

    start_discovery = st.button(
        "🧠 Start Strategy Discovery",
        type="primary",
    )

    if start_discovery:
        discovery_rows = []

        progress = st.progress(0)
        message = st.empty()

        for index, symbol in enumerate(COINS):
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

    discovery_table = st.session_state.get(
        discovery_key
    )

    if discovery_table is not None:
        display = discovery_table.copy()

        status_order = {
            "TRADE": 0,
            "WATCH": 1,
            "NO TRADE": 2,
            "NO EDGE": 3,
            "NO DATA": 4,
            "ERROR": 5,
        }

        if "Status" in display.columns:
            display["_sort"] = (
                display["Status"]
                .map(status_order)
                .fillna(9)
            )

            if "OOS PF" in display.columns:
                display = display.sort_values(
                    [
                        "_sort",
                        "OOS PF",
                    ],
                    ascending=[
                        True,
                        False,
                    ],
                )

            else:
                display = display.sort_values(
                    "_sort"
                )

            display = display.drop(
                columns=["_sort"]
            )

        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
        )

        if "Status" in display.columns:
            trade_count = int(
                (
                    display["Status"]
                    == "TRADE"
                ).sum()
            )

            watch_count = int(
                (
                    display["Status"]
                    == "WATCH"
                ).sum()
            )

        else:
            trade_count = 0
            watch_count = 0

        if trade_count:
            st.success(
                f"{trade_count} kandidaat/kandidaten "
                "halen de TRADE-drempel."
            )

        elif watch_count:
            st.warning(
                f"{watch_count} kandidaat/kandidaten "
                "zijn WATCH."
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
        data = pd.DataFrame(rows)

        if "Status" in data.columns:
            robust = data[
                data["Status"] == "ROBUST"
            ].copy()
        else:
            robust = pd.DataFrame()

        if (
            len(robust)
            and "Robustness" in robust.columns
        ):
            robust = robust.sort_values(
                "Robustness",
                ascending=False,
                na_position="last",
            )

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
            "Een kandidaat moet meerdere "
            "walk-forward periodes doorstaan "
            "en voldoende sterke finale OOS-data hebben."
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
        "Dit is alleen een onderzoeksscanner. "
        "Er worden geen echte orders geplaatst."
    )

    selected_coins = st.multiselect(
        "Coins",
        COINS,
        default=COINS[:5],
    )

    scan_button = st.button(
        "🔎 Scan nu"
    )

    if scan_button:
        scan_rows = []

        for symbol in selected_coins:
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

                params = {
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
                    "max_bars": 48,
                    "min_stop_pct": 0.35,
                    "trail_atr": 1.0,
                    "trail_trigger_r": 1.0,
                }

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

                raw_signal = "WAIT"

                if (
                    long_value
                    >= params["threshold"]
                    and long_value
                    > short_value + params["min_edge"]
                ):
                    raw_signal = "LONG"

                elif (
                    short_value
                    >= params["threshold"]
                    and short_value
                    > long_value + params["min_edge"]
                ):
                    raw_signal = "SHORT"

                allowed = saved.get(
                    "Status"
                ) in {
                    "TRADE",
                    "WATCH",
                    "ROBUST",
                }

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
                        "Long": 0,
                        "Short": 0,
                        "Error": str(exc),
                    }
                )

        st.dataframe(
            pd.DataFrame(scan_rows),
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# Footer
# ============================================================

st.divider()

st.warning(
    "Onderzoekstool. Geen financieel advies en "
    "geen live orders. Een positieve backtest "
    "is geen garantie voor toekomstige resultaten."
)
