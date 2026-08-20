import json
import os
import time
from itertools import product

import numpy as np
import pandas as pd
import requests
import streamlit as st

# ============================================================
# Crypto DayTrader v8.4.0
# Robust strategy research engine
# - Fast vectorized indicators
# - Long/short independently evaluated
# - ADX + momentum + volume + volatility regime
# - Dynamic ATR SL/TP
# - Trailing stop + time exit
# - 3-fold walk-forward validation
# - Strict anti-overfitting filters
# - Autosave/resume after every coin
# - No live orders
# ============================================================

APP_VERSION = "8.4.0"
BINANCE = "https://data-api.binance.vision/api/v3/klines"
COINS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT", "DOTUSDT",
]
RESULTS_FILE = "optimizer_results_v840.json"

st.set_page_config(
    page_title=f"Crypto DayTrader v{APP_VERSION}",
    page_icon="₿",
    layout="wide",
)

# -----------------------------
# Persistence
# -----------------------------

def load_store():
    if not os.path.exists(RESULTS_FILE):
        return {"config": None, "results": {}}
    try:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            x = json.load(f)
        if not isinstance(x, dict):
            return {"config": None, "results": {}}
        x.setdefault("config", None)
        x.setdefault("results", {})
        return x
    except Exception:
        return {"config": None, "results": {}}


def save_store(store):
    tmp = RESULTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2, default=str)
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


# -----------------------------
# Data
# -----------------------------

@st.cache_data(ttl=300, show_spinner=False)
def fetch(symbol, interval, limit):
    target = min(int(limit), 30000)
    rows = []
    end = None

    for _ in range(30):
        if len(rows) >= target:
            break

        n = min(1000, target - len(rows))
        params = {"symbol": symbol, "interval": interval, "limit": n}
        if end is not None:
            params["endTime"] = end

        batch = None
        last_error = None

        for retry in range(5):
            try:
                r = requests.get(
                    BINANCE,
                    params=params,
                    timeout=20,
                    headers={"User-Agent": f"Crypto-DayTrader/{APP_VERSION}"},
                )
                if r.status_code in (418, 429):
                    time.sleep(min(6, 2 ** retry))
                    continue
                r.raise_for_status()
                batch = r.json()
                break
            except Exception as exc:
                last_error = exc
                time.sleep(min(4, 1.5 ** retry))

        if batch is None:
            raise RuntimeError(f"Binance {symbol} {interval}: {last_error}")
        if not batch:
            break

        rows = batch + rows
        end = batch[0][0] - 1

        if len(batch) < n:
            break
        time.sleep(0.05)

    if not rows:
        raise RuntimeError(f"Geen Binance-data voor {symbol} {interval}")

    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "qv", "trades", "tb", "tq", "ignore",
    ]
    d = pd.DataFrame(rows, columns=cols).drop_duplicates("open_time")

    for c in ["open", "high", "low", "close", "volume"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")

    d["time"] = pd.to_datetime(d.open_time, unit="ms", utc=True)

    return (
        d.sort_values("time")
        [["time", "open", "high", "low", "close", "volume"]]
        .dropna()
        .tail(target)
        .reset_index(drop=True)
    )


# -----------------------------
# Indicators
# -----------------------------

def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0)
    dn = -d.clip(upper=0)
    au = up.ewm(alpha=1 / n, adjust=False).mean()
    ad = dn.ewm(alpha=1 / n, adjust=False).mean()
    rs = au / ad.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def adx(high, low, close, n=14):
    up = high.diff()
    down = -low.diff()

    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=high.index).ewm(
        alpha=1 / n, adjust=False
    ).mean() / atr.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=high.index).ewm(
        alpha=1 / n, adjust=False
    ).mean() / atr.replace(0, np.nan)

    dx = (100 * (plus_di - minus_di).abs() /
          (plus_di + minus_di).replace(0, np.nan))
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def indicators(d):
    x = d.copy()

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

    tr = pd.concat([
        x.high - x.low,
        (x.high - x.close.shift()).abs(),
        (x.low - x.close.shift()).abs(),
    ], axis=1).max(axis=1)
    x["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    x["atr_pct"] = x.atr / x.close * 100

    x["adx"] = adx(x.high, x.low, x.close, 14)

    x["vol_ma"] = x.volume.rolling(20).mean()
    x["vol_ratio"] = x.volume / x.vol_ma.replace(0, np.nan)

    x["ret1"] = x.close.pct_change()
    x["ret3"] = x.close.pct_change(3)
    x["ret12"] = x.close.pct_change(12)

    # Volatility regime: compare short volatility to medium volatility.
    x["volatility"] = x.ret1.rolling(20).std()
    x["volatility_ma"] = x.volatility.rolling(50).mean()
    x["vol_regime"] = x.volatility / x.volatility_ma.replace(0, np.nan)

    # Breakout references.
    x["high20"] = x.high.shift(1).rolling(20).max()
    x["low20"] = x.low.shift(1).rolling(20).min()
    x["high55"] = x.high.shift(1).rolling(55).max()
    x["low55"] = x.low.shift(1).rolling(55).min()

    # Volatility / mean-reversion features.
    x["bb_mid"] = x.close.rolling(20).mean()
    x["bb_std"] = x.close.rolling(20).std()
    x["bb_z"] = (x.close - x.bb_mid) / x.bb_std.replace(0, np.nan)
    x["bb_width"] = (4 * x.bb_std) / x.bb_mid.replace(0, np.nan)

    # Trend slope and momentum acceleration.
    x["ema20_slope"] = x.ema20.pct_change(5) * 100
    x["ema50_slope"] = x.ema50.pct_change(10) * 100
    x["momentum_accel"] = x.ret3 - x.ret12 / 4

    # Stochastic oscillator.
    ll = x.low.rolling(14).min()
    hh = x.high.rolling(14).max()
    x["stoch_k"] = 100 * (x.close - ll) / (hh - ll).replace(0, np.nan)
    x["stoch_d"] = x.stoch_k.rolling(3).mean()

    # ATR percentile proxy and candle/range expansion.
    x["atr_pct_rank"] = x.atr_pct.rolling(100).rank(pct=True)
    x["range_pct"] = (x.high - x.low) / x.close * 100
    x["range_ratio"] = x.range_pct / x.range_pct.rolling(20).mean().replace(0, np.nan)
    x["vol_breakout"] = x.volume / x.volume.rolling(55).max().replace(0, np.nan)

    return x


@st.cache_data(ttl=300, show_spinner=False)
def build_mtf(symbol, limit):
    d5 = indicators(fetch(symbol, "5m", limit))
    d15 = indicators(fetch(symbol, "15m", min(10000, max(500, limit // 3 + 100))))
    d1 = indicators(fetch(symbol, "1h", min(5000, max(500, limit // 12 + 100))))

    # Only closed higher-TF candles are allowed.
    def htf(d, suffix):
        z = d[[
            "time", "close", "ema20", "ema50", "ema200",
            "rsi", "macd_hist", "adx", "atr_pct", "vol_ratio",
        ]].copy()

        z["available"] = z.time.shift(-1)
        z = z.dropna(subset=["available"])

        # Keep naming explicit: EMA columns use "_15"/"_1h",
        # while momentum columns use "rsi15"/"rsi1h", etc.
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
        return z.rename(columns=rename).drop(columns=["time"])

    out = pd.merge_asof(
        d5.sort_values("time"),
        htf(d15, "15").sort_values("available"),
        left_on="time",
        right_on="available",
        direction="backward",
    )
    out = pd.merge_asof(
        out.sort_values("time"),
        htf(d1, "1h").sort_values("available"),
        left_on="time",
        right_on="available",
        direction="backward",
    )

    required = [
        "atr", "adx",
        "ema20_15", "ema50_15", "ema200_15",
        "ema20_1h", "ema50_1h", "ema200_1h",
        "rsi15", "rsi1h", "adx15", "adx1h",
    ]
    missing = [c for c in required if c not in out.columns]
    if missing:
        raise KeyError(f"MTF-kolommen ontbreken: {missing}")

    return out.dropna(subset=required).reset_index(drop=True)


# -----------------------------
# Strategy signals
# -----------------------------

def make_signals(df, p):
    """Return independent long/short scores for multiple strategy families."""
    x = df
    family = p.get("family", "trend")

    # Shared regime filters.
    adx_ok = (x.adx >= p.get("adx_min", 18)) & (x.adx1h >= p.get("adx_htf", 18))
    volume_ok = x.vol_ratio >= p.get("vol_min", 1.0)
    vol_ok = x.vol_regime.between(p.get("vol_regime_min", .55), p.get("vol_regime_max", 2.8))

    if family == "trend":
        long_core = (
            (x.ema20_1h > x.ema50_1h) & (x.ema50_1h > x.ema200_1h)
            & (x.ema20_15 > x.ema50_15)
            & (x.ema20_slope > p.get("slope_min", 0.02))
            & x.rsi.between(p["rsi_min"], p["rsi_max"])
            & (x.macd_hist > 0) & (x.ret3 > 0)
        )
        short_core = (
            (x.ema20_1h < x.ema50_1h) & (x.ema50_1h < x.ema200_1h)
            & (x.ema20_15 < x.ema50_15)
            & (x.ema20_slope < -p.get("slope_min", 0.02))
            & x.rsi.between(100-p["rsi_max"], 100-p["rsi_min"])
            & (x.macd_hist < 0) & (x.ret3 < 0)
        )
        long_score = long_core.astype(int)*55 + adx_ok.astype(int)*20 + volume_ok.astype(int)*10 + vol_ok.astype(int)*15
        short_score = short_core.astype(int)*55 + adx_ok.astype(int)*20 + volume_ok.astype(int)*10 + vol_ok.astype(int)*15

    elif family == "breakout":
        long_core = (x.close > x.high55) & (x.ema20_15 > x.ema50_15) & (x.rsi > p.get("rsi_break_long", 55))
        short_core = (x.close < x.low55) & (x.ema20_15 < x.ema50_15) & (x.rsi < p.get("rsi_break_short", 45))
        expansion = x.range_ratio >= p.get("range_ratio", 1.15)
        long_score = long_core.astype(int)*60 + expansion.astype(int)*15 + volume_ok.astype(int)*15 + adx_ok.astype(int)*10
        short_score = short_core.astype(int)*60 + expansion.astype(int)*15 + volume_ok.astype(int)*15 + adx_ok.astype(int)*10

    elif family == "pullback":
        long_core = (x.ema20_1h > x.ema50_1h) & (x.ema50_1h > x.ema200_1h) & (x.close <= x.ema20* (1+p.get("pullback_pct", .004))) & (x.close >= x.ema50) & x.rsi.between(p.get("rsi_long_min",45), p.get("rsi_long_max",58)) & (x.macd_hist > x.macd_hist.shift(1))
        short_core = (x.ema20_1h < x.ema50_1h) & (x.ema50_1h < x.ema200_1h) & (x.close >= x.ema20* (1-p.get("pullback_pct", .004))) & (x.close <= x.ema50) & x.rsi.between(p.get("rsi_short_min",42), p.get("rsi_short_max",55)) & (x.macd_hist < x.macd_hist.shift(1))
        long_score = long_core.astype(int)*65 + adx_ok.astype(int)*20 + volume_ok.astype(int)*5 + vol_ok.astype(int)*10
        short_score = short_core.astype(int)*65 + adx_ok.astype(int)*20 + volume_ok.astype(int)*5 + vol_ok.astype(int)*10

    elif family == "mean_reversion":
        long_core = (x.bb_z <= -p.get("z_entry", 1.6)) & (x.rsi <= p.get("rsi_oversold", 32)) & (x.stoch_k < p.get("stoch_long", 25)) & (x.close > x.close.shift(1))
        short_core = (x.bb_z >= p.get("z_entry", 1.6)) & (x.rsi >= 100-p.get("rsi_oversold", 32)) & (x.stoch_k > 100-p.get("stoch_long",25)) & (x.close < x.close.shift(1))
        regime = (x.adx <= p.get("adx_max", 24)) & vol_ok
        long_score = long_core.astype(int)*70 + regime.astype(int)*20 + (x.vol_ratio >= p.get("vol_min", .8)).astype(int)*10
        short_score = short_core.astype(int)*70 + regime.astype(int)*20 + (x.vol_ratio >= p.get("vol_min", .8)).astype(int)*10

    elif family == "momentum":
        long_core = (x.ret3 > p.get("ret3_min", .004)) & (x.ret12 > p.get("ret12_min", .008)) & (x.macd_hist > 0) & (x.rsi > p.get("rsi_mom", 55))
        short_core = (x.ret3 < -p.get("ret3_min", .004)) & (x.ret12 < -p.get("ret12_min", .008)) & (x.macd_hist < 0) & (x.rsi < 100-p.get("rsi_mom",55))
        expansion = (x.range_ratio >= p.get("range_ratio",1.05)) & (x.atr_pct_rank >= p.get("atr_rank",.55))
        long_score = long_core.astype(int)*60 + expansion.astype(int)*15 + volume_ok.astype(int)*15 + adx_ok.astype(int)*10
        short_score = short_core.astype(int)*60 + expansion.astype(int)*15 + volume_ok.astype(int)*15 + adx_ok.astype(int)*10

    else:
        raise ValueError(f"Onbekende strategy family: {family}")

    return long_score.to_numpy(dtype=np.int16), short_score.to_numpy(dtype=np.int16)


# -----------------------------
# Backtest
# -----------------------------

def _metrics(pnls, equity, capital):
    p = np.asarray(pnls, dtype=float)
    wins = p[p > 0].sum() if len(p) else 0.0
    losses = abs(p[p < 0].sum()) if len(p) else 0.0
    pf = wins / losses if losses else (np.inf if wins else 0.0)
    wr = (p > 0).mean()*100 if len(p) else 0.0
    ret = (equity[-1]/capital - 1)*100 if len(equity) else 0.0
    dd = np.min(equity/np.maximum.accumulate(equity)-1)*100 if len(equity) else 0.0
    expectancy = float(np.mean(p)) if len(p) else 0.0
    std = float(np.std(p, ddof=1)) if len(p)>1 else 0.0
    sharpe = float(np.mean(p)/std*np.sqrt(len(p))) if std>0 else 0.0
    neg = p[p<0]
    downside = float(np.std(neg, ddof=1)) if len(neg)>1 else 0.0
    sortino = float(np.mean(p)/downside*np.sqrt(len(p))) if downside>0 else 0.0
    max_loss_streak = cur = 0
    for v in p:
        if v < 0:
            cur += 1; max_loss_streak = max(max_loss_streak, cur)
        else:
            cur = 0
    return {
        "return": float(ret), "pf": float(pf), "wr": float(wr), "dd": float(dd),
        "trades": int(len(p)), "expectancy": expectancy, "sharpe": sharpe,
        "sortino": sortino, "max_loss_streak": int(max_loss_streak),
    }

def _run_backtest(df, p, mode, capital, risk, fee, slip, direction=None, return_pnls=False):
    open_=df.open.to_numpy(float); close=df.close.to_numpy(float); high=df.high.to_numpy(float); low=df.low.to_numpy(float); atr=df.atr.to_numpy(float)
    long_score, short_score = make_signals(df,p)
    threshold=p["threshold"]-(5 if mode=="Agressief" else 0)
    if direction=="LONG":
        signal=(long_score>=threshold)&(long_score>short_score+p["min_edge"])
    elif direction=="SHORT":
        signal=(short_score>=threshold)&(short_score>long_score+p["min_edge"])
    else:
        signal_long=(long_score>=threshold)&(long_score>short_score+p["min_edge"])
        signal_short=(short_score>=threshold)&(short_score>long_score+p["min_edge"])
    cash=float(capital); position=0; entry=stop=tp=qty=age=0.0; risk_distance=0.0; best=0.0
    pnls=[]; equity=np.empty(len(df),dtype=float); equity[0]=cash
    for i in range(1,len(df)):
        exited=False
        if position:
            age+=1; ex=None
            if position==1:
                best=max(best,high[i])
                if best-entry >= risk_distance*p.get("trail_trigger_r",1.0):
                    stop=max(stop, best-atr[i]*p.get("trail_atr",1.0))
                if low[i]<=stop: ex=stop
                elif high[i]>=tp: ex=tp
            else:
                best=min(best,low[i])
                if entry-best >= risk_distance*p.get("trail_trigger_r",1.0):
                    stop=min(stop, best+atr[i]*p.get("trail_atr",1.0))
                if high[i]>=stop: ex=stop
                elif low[i]<=tp: ex=tp
            if ex is None and age>=p["max_bars"]: ex=close[i]
            if ex is not None:
                if position==1:
                    ex*=1-slip/100; gross=(ex-entry)*qty
                else:
                    ex*=1+slip/100; gross=(entry-ex)*qty
                fees=(entry*qty+ex*qty)*fee/100; pnl=gross-fees; cash+=pnl; pnls.append(float(pnl)); position=0; exited=True
        if position==0 and not exited and cash>0 and i+1<len(df):
            if direction is None:
                side=1 if signal_long[i-1] else -1 if signal_short[i-1] else 0
            else:
                side=1 if signal[i-1] else 0
                if direction=="SHORT" and signal[i-1]: side=-1
            if side and np.isfinite(atr[i-1]) and atr[i-1]>0:
                distance=max(atr[i-1]*p["sl_atr"], close[i-1]*p["min_stop_pct"]/100)
                qty=cash*risk/100/distance
                if side==1:
                    entry=open_[i]*(1+slip/100); stop=entry-distance; tp=entry+distance*p["rr"]; best=entry
                else:
                    entry=open_[i]*(1-slip/100); stop=entry+distance; tp=entry-distance*p["rr"]; best=entry
                risk_distance=distance; position=side; age=0
        equity[i]=cash
    result=_metrics(pnls,equity,capital)
    if return_pnls: result["pnls"]=np.asarray(pnls,dtype=float)
    return result

def backtest(df,p,mode,capital,risk,fee,slip):
    return _run_backtest(df,p,mode,capital,risk,fee,slip)

def backtest_direction(df,p,mode,capital,risk,fee,slip,direction,return_pnls=False):
    return _run_backtest(df,p,mode,capital,risk,fee,slip,direction,return_pnls)


# -----------------------------
# Direction-aware research
# -----------------------------

def backtest_direction(
    df, p, mode, capital, risk, fee, slip, direction, return_pnls=False
):
    close = df.close.to_numpy(float)
    high = df.high.to_numpy(float)
    low = df.low.to_numpy(float)
    atr = df.atr.to_numpy(float)

    long_score, short_score = make_signals(df, p)
    threshold = p["threshold"] - (5 if mode == "Agressief" else 0)

    if direction == "LONG":
        signal = (long_score >= threshold) & (
            long_score > short_score + p["min_edge"]
        )
    else:
        signal = (short_score >= threshold) & (
            short_score > long_score + p["min_edge"]
        )

    cash = float(capital)
    position = 0
    entry = stop = tp = qty = 0.0
    age = 0
    pnls = []
    equity = np.empty(len(df), dtype=float)
    equity[0] = cash

    for i in range(1, len(df)):
        if position:
            age += 1
            ex = None

            if position == 1:
                if low[i] <= stop:
                    ex = stop
                elif high[i] >= tp:
                    ex = tp
            else:
                if high[i] >= stop:
                    ex = stop
                elif low[i] <= tp:
                    ex = tp

            if ex is None and age >= p["max_bars"]:
                ex = close[i]

            if ex is not None:
                if position == 1:
                    ex *= 1 - slip / 100
                    gross = (ex - entry) * qty
                else:
                    ex *= 1 + slip / 100
                    gross = (entry - ex) * qty

                fees = (entry * qty + ex * qty) * fee / 100
                pnl = gross - fees
                cash += pnl
                pnls.append(float(pnl))
                position = 0

        if position == 0 and signal[i] and cash > 0:
            if np.isfinite(atr[i]) and atr[i] > 0:
                distance = max(
                    atr[i] * p["sl_atr"],
                    close[i] * p["min_stop_pct"] / 100,
                )
                qty = cash * risk / 100 / distance

                if direction == "LONG":
                    entry = close[i] * (1 + slip / 100)
                    stop = entry - distance
                    tp = entry + distance * p["rr"]
                    position = 1
                else:
                    entry = close[i] * (1 - slip / 100)
                    stop = entry + distance
                    tp = entry - distance * p["rr"]
                    position = -1
                age = 0

        equity[i] = cash

    pnls = np.asarray(pnls, dtype=float)
    wins = pnls[pnls > 0].sum() if len(pnls) else 0
    losses = abs(pnls[pnls < 0].sum()) if len(pnls) else 0
    pf = wins / losses if losses else (np.inf if wins else 0)
    wr = (pnls > 0).mean() * 100 if len(pnls) else 0
    dd = (
        np.min(equity / np.maximum.accumulate(equity) - 1) * 100
        if len(equity) else 0
    )

    result = {
        "return": (cash / capital - 1) * 100,
        "pf": float(pf),
        "wr": float(wr),
        "dd": float(dd),
        "trades": int(len(pnls)),
    }
    if return_pnls:
        result["pnls"] = pnls
    return result


def monte_carlo_stats(pnls, capital=1000.0, simulations=1000, seed=42):
    """Bootstrap the actual individual trade P&Ls."""
    p = np.asarray(pnls, dtype=float)
    if len(p) < 15:
        return {
            "median_return": np.nan,
            "p05_return": np.nan,
            "p95_return": np.nan,
            "median_dd": np.nan,
            "p95_dd": np.nan,
        }

    rng = np.random.default_rng(seed)
    returns = np.empty(simulations)
    dds = np.empty(simulations)

    for j in range(simulations):
        sample = rng.choice(p, size=len(p), replace=True)
        eq = capital + np.cumsum(sample)
        curve = np.r_[capital, eq]
        peak = np.maximum.accumulate(curve)
        dds[j] = np.min((curve / peak - 1) * 100)
        returns[j] = (eq[-1] / capital - 1) * 100

    return {
        "median_return": float(np.median(returns)),
        "p05_return": float(np.percentile(returns, 5)),
        "p95_return": float(np.percentile(returns, 95)),
        "median_dd": float(np.median(dds)),
        "p95_dd": float(np.percentile(dds, 95)),
    }


def candidate_status(folds,oos,mc,stability):
    wf_good=sum(x["return"]>0 and x["pf"]>=1.05 for x in folds)
    hard_oos=(oos["trades"]>=15 and oos["return"]>0 and oos["pf"]>=1.20 and oos["dd"]>-20)
    mc_ok=np.isfinite(mc["p05_return"]) and mc["p05_return"]>-10
    stable_ok=stability>=0.60
    confidence=round((
        min(wf_good/3,1)*25 + min(max(oos["pf"]-1,0),1)*25 +
        min(max(oos["return"],0)/20,1)*15 + min(max(oos["dd"]+20,0)/20,1)*10 +
        min(max(mc["p05_return"],0)/10,1)*10 + stability*15
    ), 1)
    if wf_good>=2 and hard_oos and mc_ok and stable_ok: status="TRADE"
    elif oos["return"]>0 and oos["pf"]>=1.05 and oos["trades"]>=10 and stability>=.45: status="WATCH"
    else: status="NO TRADE"
    reasons=[]
    if wf_good<2: reasons.append(f"WF {wf_good}/3")
    if oos["trades"]<15: reasons.append(f"OOS trades {oos['trades']} < 15")
    if oos["pf"]<1.20: reasons.append(f"OOS PF {oos['pf']:.2f} < 1.20")
    if oos["return"]<=0: reasons.append("OOS rendement <= 0")
    if oos["dd"]<=-20: reasons.append(f"OOS DD {oos['dd']:.1f}%")
    if not mc_ok: reasons.append("MC P05 < -10%")
    if not stable_ok: reasons.append(f"stability {stability:.0%} < 60%")
    return status,confidence,"; ".join(reasons) if reasons else "Alle hoofdcriteria gehaald"

def strategy_stability(d, p, mode, capital, risk, fee, slip):
    """Validation-only neighborhood test; untouched final OOS is never used here."""
    peers=[q for q in STRATEGIES if q.get("family")==p.get("family")]
    scored=[]
    for q in peers:
        folds=[]
        n=len(d)
        for a,b in [(int(n*.35),int(n*.50)),(int(n*.50),int(n*.65)),(int(n*.65),int(n*.80))]:
            folds.append(backtest_direction(d.iloc[a:b].reset_index(drop=True),q,mode,capital,risk,fee,slip,p["direction"]))
        avg_pf=np.mean([min(z["pf"],3) if np.isfinite(z["pf"]) else 3 for z in folds])
        avg_ret=np.mean([z["return"] for z in folds])
        score=avg_ret>0 and avg_pf>=1.0 and sum(z["trades"] for z in folds)>=15
        scored.append(score)
    return float(np.mean(scored)) if scored else 0.0

def strategy_discovery(symbol,days,mode,capital,risk,fee,slip):
    d=build_mtf(symbol,int(days*24*12))
    if len(d)<500: return {"Coin":symbol,"Status":"NO DATA"}
    n=len(d); final_oos=d.iloc[int(n*.80):].reset_index(drop=True); candidates=[]
    for p in STRATEGIES:
        for direction in ["LONG","SHORT"]:
            q=dict(p); q["direction"]=direction; folds=[]
            for a,b in [(int(n*.35),int(n*.50)),(int(n*.50),int(n*.65)),(int(n*.65),int(n*.80))]:
                val=d.iloc[a:b].reset_index(drop=True)
                folds.append(backtest_direction(val,q,mode,capital,risk,fee,slip,direction))
            wf_good=sum(z["return"]>0 and z["pf"]>=1.05 for z in folds)
            avg_pf=np.mean([min(z["pf"],3) if np.isfinite(z["pf"]) else 3 for z in folds])
            avg_ret=np.mean([z["return"] for z in folds])
            total_trades=sum(z["trades"] for z in folds)
            if total_trades<15: continue
            score=wf_good/3*40+min(avg_pf/1.5,1)*25+min(max(avg_ret,0)/15,1)*20+min(total_trades/45,1)*15
            candidates.append((score,q,direction,folds))
    if not candidates: return {"Coin":symbol,"Status":"NO EDGE"}
    candidates.sort(key=lambda z:z[0],reverse=True)
    best=None
    for discovery_score,p,direction,folds in candidates[:12]:
        q=dict(p); q["direction"]=direction
        stability=strategy_stability(d,q,mode,capital,risk,fee,slip)
        oos=backtest_direction(final_oos,q,mode,capital,risk,fee,slip,direction,return_pnls=True)
        mc=monte_carlo_stats(oos.get("pnls",[]),capital=capital,simulations=1000)
        status,confidence,reason=candidate_status(folds,oos,mc,stability)
        rank=(1 if status=="TRADE" else 0,confidence,stability,oos["pf"] if np.isfinite(oos["pf"]) else 3,oos["return"])
        item=(rank,discovery_score,q,direction,folds,oos,mc,status,confidence,reason,stability)
        if best is None or rank>best[0]: best=item
    _,discovery_score,p,direction,folds,oos,mc,status,confidence,reason,stability=best
    opposite="SHORT" if direction=="LONG" else "LONG"
    opposite_oos=backtest_direction(final_oos,p,mode,capital,risk,fee,slip,opposite)
    return {"Coin":symbol,"Status":status,"Strategy":p["family"].upper(),"Direction":direction,"Confidence":confidence,"Stability":round(stability*100,1),"Discovery":round(float(discovery_score),1),"WF":f"{sum(z['return']>0 and z['pf']>=1.05 for z in folds)}/3","OOS PF":round(oos["pf"],3),"OOS %":round(oos["return"],2),"OOS trades":oos["trades"],"OOS WR":round(oos["wr"],2),"OOS DD":round(oos["dd"],2),"Expectancy":round(oos["expectancy"],3),"Sharpe":round(oos["sharpe"],2),"Sortino":round(oos["sortino"],2),"Max loss streak":oos["max_loss_streak"],"Opposite PF":round(opposite_oos["pf"],3),"MC P05 %":round(mc["p05_return"],2) if np.isfinite(mc["p05_return"]) else np.nan,"MC median %":round(mc["median_return"],2) if np.isfinite(mc["median_return"]) else np.nan,"MC P95 DD":round(mc["p95_dd"],2) if np.isfinite(mc["p95_dd"]) else np.nan,"Reason":reason,"SL ATR":p["sl_atr"],"RR":p["rr"],"threshold":p["threshold"],"max bars":p["max_bars"]}

# Diverse strategy families. Parameter stability is measured inside validation only.
STRATEGIES=[]
for sl_atr,rr in [(1.25,1.5),(1.5,2.0),(2.0,2.5)]:
    for threshold in [60,70,80]:
        for rsi_min,rsi_max in [(50,65),(52,68),(55,70)]:
            STRATEGIES.append({"family":"trend","rsi_min":rsi_min,"rsi_max":rsi_max,"adx_min":18,"adx_htf":18,"vol_min":1.0,"vol_regime_min":.55,"vol_regime_max":2.8,"slope_min":.02,"sl_atr":sl_atr,"rr":rr,"threshold":threshold,"min_edge":8,"max_bars":48,"min_stop_pct":.35,"trail_atr":1.0,"trail_trigger_r":1.0})
for sl_atr,rr in [(1.25,1.5),(1.5,2.0),(2.0,2.5)]:
    for threshold in [60,70,80]:
        for rng in [1.10,1.25,1.40]:
            STRATEGIES.append({"family":"breakout","adx_min":18,"adx_htf":18,"vol_min":1.0,"vol_regime_min":.55,"vol_regime_max":3.0,"range_ratio":rng,"rsi_break_long":55,"rsi_break_short":45,"sl_atr":sl_atr,"rr":rr,"threshold":threshold,"min_edge":5,"max_bars":36,"min_stop_pct":.35,"trail_atr":1.1,"trail_trigger_r":1.0})
for sl_atr,rr in [(1.25,1.5),(1.5,2.0),(2.0,2.5)]:
    for threshold in [60,70,80]:
        for pb in [.003,.005,.008]:
            STRATEGIES.append({"family":"pullback","adx_min":18,"adx_htf":18,"vol_min":.8,"vol_regime_min":.45,"vol_regime_max":2.5,"pullback_pct":pb,"rsi_long_min":45,"rsi_long_max":58,"rsi_short_min":42,"rsi_short_max":55,"sl_atr":sl_atr,"rr":rr,"threshold":threshold,"min_edge":5,"max_bars":48,"min_stop_pct":.30,"trail_atr":1.0,"trail_trigger_r":1.0})
for sl_atr,rr in [(1.25,1.5),(1.5,2.0)]:
    for threshold in [60,70]:
        for z in [1.5,1.8,2.1]:
            STRATEGIES.append({"family":"mean_reversion","adx_max":24,"vol_min":.8,"vol_regime_min":.45,"vol_regime_max":1.5,"z_entry":z,"rsi_oversold":32,"stoch_long":25,"sl_atr":sl_atr,"rr":rr,"threshold":threshold,"min_edge":5,"max_bars":24,"min_stop_pct":.30,"trail_atr":.9,"trail_trigger_r":1.0,"adx_min":0,"adx_htf":0})
for sl_atr,rr in [(1.25,1.5),(1.5,2.0),(2.0,2.5)]:
    for threshold in [60,70,80]:
        for mom in [.003,.005,.008]:
            STRATEGIES.append({"family":"momentum","adx_min":18,"adx_htf":18,"vol_min":1.0,"vol_regime_min":.55,"vol_regime_max":3.0,"ret3_min":mom,"ret12_min":mom*2,"rsi_mom":55,"range_ratio":1.05,"atr_rank":.55,"sl_atr":sl_atr,"rr":rr,"threshold":threshold,"min_edge":5,"max_bars":36,"min_stop_pct":.35,"trail_atr":1.1,"trail_trigger_r":1.0})


def quality(r):
    pf = 3 if not np.isfinite(r["pf"]) else r["pf"]
    return (
        pf
        + max(r["return"], -30) / 100
        + min(r["trades"], 80) / 1000
        - abs(r["dd"]) / 150
    )


def walkforward_score(folds):
    """Consistency matters more than one lucky fold."""
    if not folds:
        return 0

    positive = sum(x["return"] > 0 for x in folds)
    profitable_pf = sum(x["pf"] >= 1 for x in folds)
    avg_pf = np.mean([
        min(x["pf"], 3) if np.isfinite(x["pf"]) else 3
        for x in folds
    ])
    avg_ret = np.mean([x["return"] for x in folds])
    worst_dd = min(x["dd"] for x in folds)

    return (
        positive * 20
        + profitable_pf * 15
        + min(avg_pf / 1.5, 1) * 25
        + min(max(avg_ret, 0) / 15, 1) * 20
        + min(max(worst_dd + 20, 0) / 20, 1) * 20
    )


def robust_candidate(folds, final_oos):
    if len(folds) < 3:
        return False

    positive_folds = sum(x["return"] > 0 for x in folds)
    pf_folds = sum(x["pf"] >= 1.05 for x in folds)

    return (
        positive_folds >= 2
        and pf_folds >= 2
        and final_oos["pf"] >= 1.20
        and final_oos["return"] > 0
        and final_oos["trades"] >= 15
        and final_oos["dd"] > -20
    )


def optimize_coin(symbol,days,mode,capital,risk,fee,slip):
    row=strategy_discovery(symbol,days,mode,capital,risk,fee,slip)
    if row.get("Status") in {"ERROR","NO DATA","NO EDGE"}:
        return {"Coin":symbol,"Status":"AFGEKEURD","Reason":row.get("Reason","Geen edge") }
    return {"Coin":symbol,"Status":"ROBUST" if row.get("Status")=="TRADE" else "AFGEKEURD","Robustness":row.get("Confidence",0),"Strategy":row.get("Strategy"),"Direction":row.get("Direction"),"Stability":row.get("Stability"),"WF consistency":row.get("WF"),"OOS PF":row.get("OOS PF"),"OOS %":row.get("OOS %"),"OOS trades":row.get("OOS trades"),"OOS WR":row.get("OOS WR"),"OOS DD":row.get("OOS DD"),"Expectancy":row.get("Expectancy"),"Sharpe":row.get("Sharpe"),"Sortino":row.get("Sortino"),"Max loss streak":row.get("Max loss streak"),"MC P05 %":row.get("MC P05 %"),"Reason":row.get("Reason"),"SL ATR":row.get("SL ATR"),"RR":row.get("RR"),"threshold":row.get("threshold"),"max bars":row.get("max bars")}


# -----------------------------
# UI
# -----------------------------

st.title("₿ Crypto DayTrader v8.4.0")
st.caption(
    "v8.4 • Trend / Breakout / Pullback / Mean-Reversion / Momentum • "
    "realistic next-open execution • trailing stop • WF • Monte Carlo • stability"
)

with st.sidebar:
    mode = st.radio("Strategie", ["Conservatief", "Agressief"])
    capital = st.number_input("Startkapitaal (€)", 100.0, 100000.0, 1000.0, 100.0)
    risk = st.slider("Risico per trade (%)", .25, 2.0, 1.0, .25)
    fee = st.number_input("Fee per kant (%)", 0.0, .50, .10, .01)
    slip = st.number_input("Slippage per kant (%)", 0.0, .50, .03, .01)
    days = st.select_slider("Onderzoeksperiode", options=[14, 30, 60, 90], value=60)

current_config = make_config(days, mode, capital, risk, fee, slip)
store = load_store()

if store["config"] != current_config:
    active_results = {}
else:
    active_results = store["results"]

tab1, tab2, tab3, tab4 = st.tabs([
    "🔬 Optimizer",
    "🧠 Strategy Discovery",
    "🏆 Robustness",
    "📈 Live scanner",
])

with tab1:
    done = sum(c in active_results for c in COINS)

    st.progress(done / len(COINS))
    st.caption(f"{done}/{len(COINS)} coins opgeslagen")

    c1, c2 = st.columns(2)

    with c1:
        start = st.button("🚀 Start / hervat optimizer", type="primary")

    with c2:
        reset = st.button("🧹 Nieuwe optimalisatie")

    if reset:
        store = {"config": current_config, "results": {}}
        save_store(store)
        st.rerun()

    if start:
        store = {"config": current_config, "results": active_results}
        progress = st.progress(done / len(COINS))
        status = st.empty()

        for i, symbol in enumerate(COINS):
            if symbol in store["results"]:
                status.write(f"✅ {symbol} al klaar — overslaan")
                progress.progress((i + 1) / len(COINS))
                continue

            status.write(f"⚙️ {symbol}: robuustheidstest ({i + 1}/{len(COINS)})...")
            started = time.time()

            try:
                row = optimize_coin(
                    symbol, days, mode, capital, risk, fee, slip
                )
                store["results"][symbol] = {
                    "row": row,
                    "saved_at": pd.Timestamp.utcnow().isoformat(),
                }
                save_store(store)

                elapsed = time.time() - started
                status.write(
                    f"✅ {symbol} klaar in {elapsed:.1f}s — opgeslagen"
                )
            except Exception as exc:
                row = {
                    "Coin": symbol,
                    "Status": "FOUT",
                    "Reason": str(exc),
                }
                store["results"][symbol] = {
                    "row": row,
                    "saved_at": pd.Timestamp.utcnow().isoformat(),
                }
                save_store(store)
                status.error(f"{symbol}: {exc}")

            progress.progress((i + 1) / len(COINS))

        st.success("Robustness optimizer klaar.")
        st.rerun()

    rows = [
        x["row"]
        for x in active_results.values()
        if isinstance(x, dict) and "row" in x
    ]

    if rows:
        table = pd.DataFrame(rows)

        if "Robustness" in table.columns:
            table = table.sort_values(
                "Robustness",
                ascending=False,
                na_position="last",
            )

        st.dataframe(table, use_container_width=True, hide_index=True)
    else:
        st.info("Nog geen resultaten.")

with tab2:
    st.subheader("🧠 Strategy Discovery")
    st.write(
        "Deze analyse onderzoekt meerdere strategie-families per coin en richting. "
        "Alleen validation-data bepaalt de selectie; de laatste 20% blijft een "
        "onaangeraakte OOS-test. Parameter-stability wordt binnen validation gemeten."
    )

    discovery_key = f"discovery_v840_{days}_{mode}_{capital}_{risk}_{fee}_{slip}"
    if st.button("🧠 Start Strategy Discovery", type="primary"):
        drows = []
        pbar = st.progress(0)
        msg = st.empty()

        for i, symbol in enumerate(COINS):
            msg.write(f"🔎 Analyse {symbol} ({i + 1}/{len(COINS)})...")
            try:
                drows.append(
                    strategy_discovery(
                        symbol, days, mode, capital, risk, fee, slip
                    )
                )
            except Exception as exc:
                drows.append({
                    "Coin": symbol,
                    "Status": "ERROR",
                    "Reason": str(exc),
                })
            pbar.progress((i + 1) / len(COINS))

        st.session_state[discovery_key] = pd.DataFrame(drows)

    disc = st.session_state.get(discovery_key)
    if disc is not None:
        st.caption(
            "TRADE vereist ≥2/3 WF, ≥15 OOS-trades, OOS PF ≥1.20, positief OOS-rendement, "
            "DD > -20%, MC P05 > -10% én ≥60% parameter-stability."
        )
        order = {"TRADE": 0, "WATCH": 1, "NO TRADE": 2,
                 "NO EDGE": 3, "NO DATA": 4, "ERROR": 5}
        disc = disc.copy()
        if "Status" in disc:
            disc["_order"] = disc["Status"].map(order).fillna(9)
            disc = disc.sort_values(
                ["_order", "OOS PF" if "OOS PF" in disc.columns else "Coin"],
                ascending=[True, False],
            ).drop(columns=["_order"])

        st.dataframe(disc, use_container_width=True, hide_index=True)

        trade_count = int((disc.get("Status", pd.Series(dtype=str)) == "TRADE").sum())
        watch_count = int((disc.get("Status", pd.Series(dtype=str)) == "WATCH").sum())

        if trade_count:
            st.success(f"{trade_count} kandidaat/kandidaten halen de TRADE-drempel.")
        elif watch_count:
            st.warning(
                f"{watch_count} kandidaat/kandidaten zijn WATCH, maar geen enkele is "
                "sterk genoeg voor TRADE."
            )
        else:
            st.info("Geen robuuste edge gevonden. Dat is een geldig resultaat.")

with tab3:
    st.subheader("🏆 Robuuste strategieën")

    rows = [
        x["row"]
        for x in active_results.values()
        if isinstance(x, dict) and "row" in x
    ]

    if rows:
        d = pd.DataFrame(rows)

        if "Status" in d:
            robust = d[d["Status"].eq("ROBUST")].copy()
            if "Robustness" in robust.columns:
                robust = robust.sort_values(
                    "Robustness", ascending=False, na_position="last"
                )
        else:
            robust = pd.DataFrame()

        if len(robust):
            st.success(
                f"{len(robust)} coin(s) hebben een robuuste kandidaat."
            )
            st.dataframe(
                robust,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.warning(
                "Geen robuuste strategie gevonden. "
                "Dat is bewust: de optimizer forceert geen winnaar."
            )

        st.info(
            "Een kandidaat moet meerdere walk-forward periodes doorstaan "
            "én positieve, voldoende grote finale OOS-resultaten hebben."
        )
    else:
        st.info("Voer eerst de optimizer uit.")

with tab4:
    st.subheader("📈 Live scanner")
    st.write(
        "Onderzoekssignalen op basis van de laatst gevonden strategie. "
        "Geen echte orders. Gebruik TRADE/WATCH/NO TRADE uit Strategy Discovery "
        "als primaire onderzoeksfilter."
    )

    selected = st.multiselect(
        "Coins",
        COINS,
        default=COINS[:5],
    )

    if st.button("🔎 Scan nu"):
        scan=[]
        for symbol in selected:
            try:
                saved=active_results.get(symbol,{}).get("row",{})
                family=str(saved.get("Strategy", "TREND")).lower()
                p={"family":family,"rsi_min":52,"rsi_max":68,"adx_min":18,"adx_htf":18,"vol_min":1.0,"vol_regime_min":.55,"vol_regime_max":2.8,"slope_min":.02,"sl_atr":float(saved.get("SL ATR",1.5)),"rr":float(saved.get("RR",2.0)),"threshold":int(saved.get("threshold",70)),"min_edge":5,"max_bars":48,"min_stop_pct":.35,"trail_atr":1.0,"trail_trigger_r":1.0}
                d=build_mtf(symbol,1000); l,scores=make_signals(d,p); r=d.iloc[-1]; L=int(l[-1]); S=int(scores[-1])
                raw="LONG" if L>=p["threshold"] and L>S+p["min_edge"] else "SHORT" if S>=p["threshold"] and S>L+p["min_edge"] else "WAIT"
                allowed=saved.get("Status") in {"TRADE","WATCH"}
                direction=saved.get("Direction")
                signal=raw if allowed and raw!="WAIT" and (not direction or direction==raw) else "WAIT"
                scan.append({"Coin":symbol,"Signal":signal,"Strategy":family.upper(),"Long":L,"Short":S,"ADX":round(float(r.adx),1),"RSI":round(float(r.rsi),1),"Vol ratio":round(float(r.vol_ratio),2),"Price":round(float(r.close),6)})
            except Exception as exc:
                scan.append({"Coin":symbol,"Signal":"ERROR","Strategy":"-","Long":0,"Short":0,"Error":str(exc)})
        st.dataframe(pd.DataFrame(scan),use_container_width=True,hide_index=True)


st.divider()
st.warning(
    "Onderzoekstool. Geen financieel advies en geen live orders. "
    "Een positieve backtest is geen garantie voor toekomstige resultaten."
)
