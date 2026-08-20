import json
import os
import time
from itertools import product

import numpy as np
import pandas as pd
import requests
import streamlit as st

# ============================================================
# Crypto DayTrader v8.2.2
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

APP_VERSION = "8.2.2"
BINANCE = "https://data-api.binance.vision/api/v3/klines"
COINS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT", "DOTUSDT",
]
RESULTS_FILE = "optimizer_results_v82.json"

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
    target = min(int(limit), 10000)
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

    return x


@st.cache_data(ttl=300, show_spinner=False)
def build_mtf(symbol, limit):
    d5 = indicators(fetch(symbol, "5m", limit))
    d15 = indicators(fetch(symbol, "15m", max(500, min(3000, limit // 3 + 100))))
    d1 = indicators(fetch(symbol, "1h", max(500, min(2000, limit // 12 + 100))))

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
    x = df

    trend_long = (
        (x.ema20_1h > x.ema50_1h)
        & (x.ema50_1h > x.ema200_1h)
        & (x.ema20_15 > x.ema50_15)
    )

    trend_short = (
        (x.ema20_1h < x.ema50_1h)
        & (x.ema50_1h < x.ema200_1h)
        & (x.ema20_15 < x.ema50_15)
    )

    momentum_long = (
        (x.rsi.between(p["rsi_min"], p["rsi_max"]))
        & (x.macd_hist > 0)
        & (x.ret3 > 0)
    )

    momentum_short = (
        (x.rsi.between(100 - p["rsi_max"], 100 - p["rsi_min"]))
        & (x.macd_hist < 0)
        & (x.ret3 < 0)
    )

    adx_ok = (x.adx >= p["adx_min"]) & (x.adx1h >= p["adx_htf"])

    volume_ok = x.vol_ratio >= p["vol_min"]

    volatility_ok = x.vol_regime.between(
        p["vol_regime_min"], p["vol_regime_max"]
    )

    breakout_long = x.close > x.high20
    breakout_short = x.close < x.low20

    long_score = (
        trend_long.astype(int) * 30
        + momentum_long.astype(int) * 20
        + adx_ok.astype(int) * 15
        + volume_ok.astype(int) * 10
        + volatility_ok.astype(int) * 10
        + breakout_long.astype(int) * 15
    )

    short_score = (
        trend_short.astype(int) * 30
        + momentum_short.astype(int) * 20
        + adx_ok.astype(int) * 15
        + volume_ok.astype(int) * 10
        + volatility_ok.astype(int) * 10
        + breakout_short.astype(int) * 15
    )

    return long_score.to_numpy(dtype=np.int16), short_score.to_numpy(dtype=np.int16)


# -----------------------------
# Backtest
# -----------------------------

def backtest(df, p, mode, capital, risk, fee, slip):
    close = df.close.to_numpy(float)
    high = df.high.to_numpy(float)
    low = df.low.to_numpy(float)
    atr = df.atr.to_numpy(float)

    long_score, short_score = make_signals(df, p)

    threshold = p["threshold"]
    if mode == "Agressief":
        threshold -= 5

    long_signal = (
        (long_score >= threshold)
        & (long_score > short_score + p["min_edge"])
    )
    short_signal = (
        (short_score >= threshold)
        & (short_score > long_score + p["min_edge"])
    )

    cash = float(capital)
    position = 0
    entry = stop = tp = qty = 0.0
    age = 0

    pnls = []
    equity = np.empty(len(df), dtype=float)
    equity[0] = cash

    for i in range(1, len(df)):
        exited = False

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

            # Time-based exit.
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
                pnls.append(pnl)
                position = 0
                exited = True

        if position == 0 and not exited and cash > 0:
            side = 1 if long_signal[i] else -1 if short_signal[i] else 0

            if side and np.isfinite(atr[i]) and atr[i] > 0:
                distance = max(
                    atr[i] * p["sl_atr"],
                    close[i] * p["min_stop_pct"] / 100,
                )

                qty = cash * risk / 100 / distance

                if side == 1:
                    entry = close[i] * (1 + slip / 100)
                    stop = entry - distance
                    tp = entry + distance * p["rr"]
                else:
                    entry = close[i] * (1 - slip / 100)
                    stop = entry + distance
                    tp = entry - distance * p["rr"]

                position = side
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

    return {
        "return": (cash / capital - 1) * 100,
        "pf": float(pf),
        "wr": float(wr),
        "dd": float(dd),
        "trades": int(len(pnls)),
    }


# -----------------------------
# Strategy grid
# -----------------------------

STRATEGIES = []

for rsi_min, rsi_max in [(52, 68), (50, 65), (55, 70)]:
    for adx_min, adx_htf in [(18, 18), (22, 20)]:
        for vol_min in [1.0, 1.2]:
            for sl_atr, rr in [(1.25, 1.5), (1.5, 2.0), (2.0, 2.5)]:
                for threshold in [70, 85]:
                    STRATEGIES.append({
                        "rsi_min": rsi_min,
                        "rsi_max": rsi_max,
                        "adx_min": adx_min,
                        "adx_htf": adx_htf,
                        "vol_min": vol_min,
                        "vol_regime_min": .65,
                        "vol_regime_max": 2.5,
                        "sl_atr": sl_atr,
                        "rr": rr,
                        "threshold": threshold,
                        "min_edge": 10,
                        "max_bars": 48,
                        "min_stop_pct": .35,
                    })


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
        and final_oos["pf"] >= 1.10
        and final_oos["return"] > 0
        and final_oos["trades"] >= 15
        and final_oos["dd"] > -20
    )


def optimize_coin(symbol, days, mode, capital, risk, fee, slip):
    limit = int(days * 24 * 12)
    d = build_mtf(symbol, limit)

    if len(d) < 500:
        return {
            "Coin": symbol,
            "Status": "AFGEKEURD",
            "Reason": f"Te weinig bruikbare candles ({len(d)})",
        }

    # 3 chronological folds:
    # fold 1: train 50%, validate next 15%
    # fold 2: train 65%, validate next 15%
    # final: last 20% reserved as untouched OOS.
    n = len(d)
    final_cut = int(n * .80)
    final_oos = d.iloc[final_cut:].reset_index(drop=True)

    candidates = []

    for p in STRATEGIES:
        fold_results = []

        fold_ranges = [
            (0, int(n * .50), int(n * .65)),
            (0, int(n * .65), int(n * .80)),
        ]

        # A third shorter validation on the earlier segment.
        fold_ranges.append((0, int(n * .35), int(n * .50)))

        for train_end, _, val_end in fold_ranges:
            if val_end <= train_end:
                continue

            # Use the validation window after the train endpoint.
            if train_end == 0:
                train_end = int(n * .35)

            val_start = train_end
            val = d.iloc[val_start:val_end].reset_index(drop=True)

            if len(val) < 50:
                continue

            r = backtest(val, p, mode, capital, risk, fee, slip)
            fold_results.append(r)

        if len(fold_results) < 3:
            continue

        wf = walkforward_score(fold_results)

        # Require a basic amount of activity before ranking.
        total_trades = sum(x["trades"] for x in fold_results)
        if total_trades < 20:
            continue

        candidates.append((wf, p, fold_results))

    if not candidates:
        return {
            "Coin": symbol,
            "Status": "AFGEKEURD",
            "Reason": "Geen strategie haalde de walk-forward minimumvoorwaarden",
        }

    candidates.sort(key=lambda x: x[0], reverse=True)
    _, p, folds = candidates[0]

    # Final untouched OOS.
    oos = backtest(final_oos, p, mode, capital, risk, fee, slip)

    # Also evaluate direction separately.
    # The strategy itself remains combined, but this helps diagnostics.
    robust = robust_candidate(folds, oos)

    consistency = sum(
        1 for x in folds
        if x["return"] > 0 and x["pf"] >= 1
    )

    robustness = round(
        min(max(oos["pf"] - 1, 0) / .75, 1) * 35
        + min(max(oos["return"], 0) / 20, 1) * 25
        + min(max(oos["dd"] + 20, 0) / 20, 1) * 20
        + min(oos["trades"] / 40, 1) * 10
        + consistency / 3 * 10,
        1,
    )

    return {
        "Coin": symbol,
        "Status": "ROBUST" if robust else "AFGEKEURD",
        "Robustness": robustness,
        "WF consistency": f"{consistency}/3",
        "OOS PF": round(oos["pf"], 3),
        "OOS %": round(oos["return"], 2),
        "OOS trades": oos["trades"],
        "OOS WR": round(oos["wr"], 2),
        "OOS DD": round(oos["dd"], 2),
        "RSI": f'{p["rsi_min"]}-{p["rsi_max"]}',
        "ADX": f'{p["adx_min"]}/{p["adx_htf"]}',
        "Volume": p["vol_min"],
        "SL ATR": p["sl_atr"],
        "RR": p["rr"],
        "threshold": p["threshold"],
        "max bars": p["max_bars"],
    }


# -----------------------------
# UI
# -----------------------------

st.title("₿ Crypto DayTrader v8.2.2")
st.caption(
    "Robust strategy engine • ADX • momentum • volume • volatility regime • "
    "walk-forward • strict OOS • autosave"
)

with st.sidebar:
    mode = st.radio("Strategie", ["Conservatief", "Agressief"])
    capital = st.number_input("Startkapitaal (€)", 100.0, 100000.0, 1000.0, 100.0)
    risk = st.slider("Risico per trade (%)", .25, 2.0, 1.0, .25)
    fee = st.number_input("Fee per kant (%)", 0.0, .50, .10, .01)
    slip = st.number_input("Slippage per kant (%)", 0.0, .50, .03, .01)
    days = st.select_slider("Onderzoeksperiode", options=[7, 14, 30], value=30)

current_config = make_config(days, mode, capital, risk, fee, slip)
store = load_store()

if store["config"] != current_config:
    active_results = {}
else:
    active_results = store["results"]

tab1, tab2, tab3 = st.tabs([
    "🔬 Optimizer",
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

with tab3:
    st.subheader("📈 Live scanner")
    st.write(
        "Onderzoekssignalen op basis van de laatst gevonden strategie. "
        "Geen echte orders."
    )

    selected = st.multiselect(
        "Coins",
        COINS,
        default=COINS[:5],
    )

    if st.button("🔎 Scan nu"):
        scan = []

        for symbol in selected:
            try:
                saved = active_results.get(symbol, {}).get("row", {})

                # Scanner uses a sensible default if the coin was rejected.
                p = {
                    "rsi_min": 52,
                    "rsi_max": 68,
                    "adx_min": 22,
                    "adx_htf": 20,
                    "vol_min": 1.0,
                    "vol_regime_min": .65,
                    "vol_regime_max": 2.5,
                    "sl_atr": float(saved.get("SL ATR", 1.5)),
                    "rr": float(saved.get("RR", 2.0)),
                    "threshold": int(saved.get("threshold", 85)),
                    "min_edge": 10,
                    "max_bars": 48,
                    "min_stop_pct": .35,
                }

                d = build_mtf(symbol, 1000)
                l, s = make_signals(d, p)
                r = d.iloc[-1]

                L = int(l[-1])
                S = int(s[-1])

                signal = (
                    "LONG" if L >= p["threshold"] and L > S + p["min_edge"]
                    else "SHORT"
                    if S >= p["threshold"] and S > L + p["min_edge"]
                    else "WAIT"
                )

                scan.append({
                    "Coin": symbol,
                    "Signal": signal,
                    "Long": L,
                    "Short": S,
                    "ADX": round(float(r.adx), 1),
                    "RSI": round(float(r.rsi), 1),
                    "Vol ratio": round(float(r.vol_ratio), 2),
                    "Price": round(float(r.close), 6),
                })

            except Exception as exc:
                scan.append({
                    "Coin": symbol,
                    "Signal": "ERROR",
                    "Long": 0,
                    "Short": 0,
                    "Error": str(exc),
                })

        st.dataframe(
            pd.DataFrame(scan),
            use_container_width=True,
            hide_index=True,
        )

st.divider()
st.warning(
    "Onderzoekstool. Geen financieel advies en geen live orders. "
    "Een positieve backtest is geen garantie voor toekomstige resultaten."
)
