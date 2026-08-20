
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# ============================================================
# Crypto DayTrader — Complete mobile paper-trading dashboard
# ============================================================

st.set_page_config(
    page_title="Crypto DayTrader",
    page_icon="₿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

BINANCE = "https://data-api.binance.vision/api/v3/klines"
INTERVALS = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600}
DEFAULT_COINS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT", "DOTUSDT",
]

# --------------------------- Data ----------------------------

@st.cache_data(ttl=20, show_spinner=False)
def get_klines(symbol: str, interval: str, limit: int = 1000):
    """Fetch public Binance market candles without an API key."""
    rows = []
    end_time = None

    # Binance limit is normally 1000. Paginate backwards when more is requested.
    remaining = int(min(limit, 3000))
    while remaining > 0:
        batch_limit = min(1000, remaining)
        params = {"symbol": symbol, "interval": interval, "limit": batch_limit}
        if end_time is not None:
            params["endTime"] = end_time

        r = requests.get(
            BINANCE,
            params=params,
            timeout=15,
            headers={"User-Agent": "Crypto-DayTrader/3.0"},
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break

        rows = batch + rows
        oldest = batch[0][0]
        end_time = oldest - 1
        remaining -= len(batch)

        if len(batch) < batch_limit:
            break

    if not rows:
        raise ValueError("Geen marktdata ontvangen.")

    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore",
    ]
    df = pd.DataFrame(rows, columns=cols).drop_duplicates("open_time")
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df.sort_values("time").tail(limit)[
        ["time", "open", "high", "low", "close", "volume"]
    ].dropna().reset_index(drop=True)


# ------------------------ Indicators --------------------------

def rsi(s, n=14):
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    ag = gain.ewm(alpha=1/n, adjust=False).mean()
    al = loss.ewm(alpha=1/n, adjust=False).mean()
    rs = ag / al.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df, n=14):
    tr = pd.concat(
        [
            df.high - df.low,
            (df.high - df.close.shift()).abs(),
            (df.low - df.close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()


def indicators(df):
    x = df.copy()
    x["ema9"] = x.close.ewm(span=9, adjust=False).mean()
    x["ema21"] = x.close.ewm(span=21, adjust=False).mean()
    x["ema50"] = x.close.ewm(span=50, adjust=False).mean()
    x["ema200"] = x.close.ewm(span=200, adjust=False).mean()
    x["rsi"] = rsi(x.close)

    e12 = x.close.ewm(span=12, adjust=False).mean()
    e26 = x.close.ewm(span=26, adjust=False).mean()
    x["macd"] = e12 - e26
    x["macd_signal"] = x.macd.ewm(span=9, adjust=False).mean()
    x["macd_hist"] = x.macd - x.macd_signal

    x["atr"] = atr(x)
    x["atr_pct"] = x.atr / x.close * 100
    x["vol_ma"] = x.volume.rolling(20).mean()

    # ADX / directional movement
    up = x.high.diff()
    down = -x.low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = pd.concat(
        [
            x.high - x.low,
            (x.high - x.close.shift()).abs(),
            (x.low - x.close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr14 = tr.ewm(alpha=1/14, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=x.index).ewm(alpha=1/14, adjust=False).mean() / atr14
    minus_di = 100 * pd.Series(minus_dm, index=x.index).ewm(alpha=1/14, adjust=False).mean() / atr14
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100
    x["adx"] = dx.ewm(alpha=1/14, adjust=False).mean()

    return x


# ------------------------- Strategy ---------------------------

def analyse(row, mode="Conservatief"):
    """Directional score. Maximum 100."""
    long_score = 0
    short_score = 0
    long_reasons = []
    short_reasons = []

    # Trend: 25 points
    if row.ema9 > row.ema21:
        long_score += 10; long_reasons.append("EMA9 > EMA21")
    elif row.ema9 < row.ema21:
        short_score += 10; short_reasons.append("EMA9 < EMA21")

    if row.close > row.ema50:
        long_score += 10; long_reasons.append("prijs > EMA50")
    elif row.close < row.ema50:
        short_score += 10; short_reasons.append("prijs < EMA50")

    if row.close > row.ema200:
        long_score += 5; long_reasons.append("prijs > EMA200")
    elif row.close < row.ema200:
        short_score += 5; short_reasons.append("prijs < EMA200")

    # Momentum: 30 points
    if row.macd > row.macd_signal:
        long_score += 15; long_reasons.append("MACD bullish")
    elif row.macd < row.macd_signal:
        short_score += 15; short_reasons.append("MACD bearish")

    if 50 <= row.rsi <= 68:
        long_score += 15; long_reasons.append("RSI long-zone")
    elif 32 <= row.rsi <= 50:
        short_score += 10; short_reasons.append("RSI short-zone")
    elif row.rsi < 30:
        long_score += 5; long_reasons.append("RSI oversold")
    elif row.rsi > 70:
        short_score += 5; short_reasons.append("RSI overbought")

    # Trend strength: 15 points
    if row.adx >= 20:
        if row.ema9 > row.ema21:
            long_score += 15; long_reasons.append(f"ADX sterk ({row.adx:.0f})")
        elif row.ema9 < row.ema21:
            short_score += 15; short_reasons.append(f"ADX sterk ({row.adx:.0f})")

    # Volume: 10 points
    if pd.notna(row.vol_ma) and row.volume > row.vol_ma * 1.15:
        if row.close >= row.open:
            long_score += 10; long_reasons.append("sterk bullish volume")
        else:
            short_score += 10; short_reasons.append("sterk bearish volume")

    # Volatility filter: avoid dead markets
    if 0.15 <= row.atr_pct <= 4.0:
        long_score += 5
        short_score += 5

    threshold = 70 if mode == "Conservatief" else 55
    best = max(long_score, short_score)

    if best >= threshold and long_score > short_score + 5:
        signal = "LONG"
    elif best >= threshold and short_score > long_score + 5:
        signal = "SHORT"
    else:
        signal = "WAIT"

    return {
        "long": int(min(long_score, 100)),
        "short": int(min(short_score, 100)),
        "score": int(best),
        "signal": signal,
        "threshold": threshold,
        "long_reasons": long_reasons,
        "short_reasons": short_reasons,
    }


def trade_plan(row, signal, capital, risk_pct, mode):
    if signal not in ("LONG", "SHORT"):
        return None

    entry = float(row.close)
    # ATR stop, with a minimum distance to avoid microscopic stops.
    stop_dist = max(float(row.atr) * 1.25, entry * 0.004)
    rr = 2.2 if mode == "Conservatief" else 1.7
    risk_cash = capital * risk_pct / 100
    qty = risk_cash / stop_dist if stop_dist > 0 else 0

    if signal == "LONG":
        stop = entry - stop_dist
        tp1 = entry + stop_dist * 1.0
        tp2 = entry + stop_dist * rr
    else:
        stop = entry + stop_dist
        tp1 = entry - stop_dist * 1.0
        tp2 = entry - stop_dist * rr

    return {
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "qty": qty,
        "risk_cash": risk_cash,
        "rr": rr,
        "notional": qty * entry,
    }


# ------------------------- Backtest --------------------------

def backtest(df, mode, starting_capital, risk_pct, fee_pct=0.10, slippage_pct=0.03):
    x = indicators(df).dropna().reset_index(drop=True)
    cash = float(starting_capital)
    equity = []
    trades = []
    pos = None

    for i in range(len(x)):
        row = x.iloc[i]
        a = analyse(row, mode)

        if pos is None:
            if a["signal"] in ("LONG", "SHORT"):
                plan = trade_plan(row, a["signal"], cash, risk_pct, mode)
                pos = {
                    "side": a["signal"],
                    "entry": plan["entry"] * (1 + slippage_pct/100 if a["signal"] == "LONG" else 1 - slippage_pct/100),
                    "stop": plan["stop"],
                    "tp2": plan["tp2"],
                    "qty": plan["qty"],
                    "entry_time": row.time,
                }
        else:
            exit_price = None
            reason = None

            if pos["side"] == "LONG":
                if row.low <= pos["stop"]:
                    exit_price, reason = pos["stop"], "stop-loss"
                elif row.high >= pos["tp2"]:
                    exit_price, reason = pos["tp2"], "take-profit"
            else:
                if row.high >= pos["stop"]:
                    exit_price, reason = pos["stop"], "stop-loss"
                elif row.low <= pos["tp2"]:
                    exit_price, reason = pos["tp2"], "take-profit"

            if exit_price is not None:
                exit_price *= (1 - slippage_pct/100 if pos["side"] == "LONG" else 1 + slippage_pct/100)
                if pos["side"] == "LONG":
                    pnl = (exit_price - pos["entry"]) * pos["qty"]
                else:
                    pnl = (pos["entry"] - exit_price) * pos["qty"]
                # Approximate round-trip fees.
                pnl -= abs(pos["entry"] * pos["qty"]) * fee_pct/100
                pnl -= abs(exit_price * pos["qty"]) * fee_pct/100
                cash += pnl
                trades.append({
                    "Side": pos["side"],
                    "Entry": pos["entry"],
                    "Exit": exit_price,
                    "P&L": pnl,
                    "Reason": reason,
                    "Entry time": pos["entry_time"],
                    "Exit time": row.time,
                })
                pos = None

        equity.append(cash)

    t = pd.DataFrame(trades)
    if len(t):
        wins = int((t["P&L"] > 0).sum())
        winrate = wins / len(t) * 100
        gross_profit = t.loc[t["P&L"] > 0, "P&L"].sum()
        gross_loss = abs(t.loc[t["P&L"] < 0, "P&L"].sum())
        profit_factor = gross_profit / gross_loss if gross_loss else np.inf
    else:
        winrate = 0.0
        profit_factor = 0.0

    eq = pd.Series(equity)
    peak = eq.cummax()
    drawdown = (eq - peak) / peak * 100
    max_dd = float(drawdown.min()) if len(eq) else 0.0

    return {
        "final": cash,
        "pnl": cash - starting_capital,
        "return_pct": (cash / starting_capital - 1) * 100,
        "trades": t,
        "winrate": winrate,
        "profit_factor": profit_factor,
        "max_drawdown": max_dd,
    }


# ----------------------- Paper trading -----------------------

def init_state():
    if "paper_cash" not in st.session_state:
        st.session_state.paper_cash = 1000.0
    if "paper_position" not in st.session_state:
        st.session_state.paper_position = None
    if "paper_trades" not in st.session_state:
        st.session_state.paper_trades = []


def execute_paper(plan, symbol, signal):
    if st.session_state.paper_position is not None:
        return "Er staat al een paper trade open."

    st.session_state.paper_position = {
        "symbol": symbol,
        "side": signal,
        "entry": plan["entry"],
        "stop": plan["stop"],
        "tp1": plan["tp1"],
        "tp2": plan["tp2"],
        "qty": plan["qty"],
        "opened": datetime.now(timezone.utc).isoformat(),
    }
    return "Paper trade geopend."


def close_paper(price):
    p = st.session_state.paper_position
    if not p:
        return
    if p["side"] == "LONG":
        pnl = (price - p["entry"]) * p["qty"]
    else:
        pnl = (p["entry"] - price) * p["qty"]
    st.session_state.paper_cash += pnl
    st.session_state.paper_trades.append({
        "Symbol": p["symbol"], "Side": p["side"],
        "Entry": p["entry"], "Exit": price, "P&L": pnl,
        "Opened": p["opened"], "Closed": datetime.now(timezone.utc).isoformat()
    })
    st.session_state.paper_position = None


init_state()

# ---------------------------- UI -----------------------------

with st.sidebar:
    st.header("⚙️ Instellingen")
    mode = st.radio("Strategie", ["Conservatief", "Agressief"])
    interval = st.selectbox("Timeframe", list(INTERVALS.keys()), index=2)
    capital = st.number_input("Analyse-kapitaal (€)", 100.0, 100000.0, 1000.0, 100.0)
    risk_pct = st.slider("Risico per trade (%)", 0.25, 3.0, 1.0, 0.25)
    coins_text = st.text_area("Scanner", "\n".join(DEFAULT_COINS))
    candles_count = st.select_slider("Historische candles", options=[300, 500, 1000, 2000, 3000], value=1000)

    if st.button("🔄 Vernieuw data"):
        st.cache_data.clear()
        st.rerun()

coins = [x.strip().upper().replace("/", "") for x in coins_text.splitlines() if x.strip()]

st.title("₿ Crypto DayTrader")
st.caption("Scanner • signalen • trade-plan • backtest • paper trading")

# Scanner
st.subheader("🔎 Markt Scanner")
rows = []
with st.spinner("Markten analyseren..."):
    for symbol in coins:
        try:
            d = indicators(get_klines(symbol, interval, 300))
            r = d.iloc[-1]
            a = analyse(r, mode)
            rows.append({
                "Coin": symbol,
                "Prijs": float(r.close),
                "Score": a["score"],
                "LONG": a["long"],
                "SHORT": a["short"],
                "Signaal": "🟢 LONG" if a["signal"] == "LONG" else ("🔴 SHORT" if a["signal"] == "SHORT" else "🟡 WACHTEN"),
                "RSI": float(r.rsi),
                "ADX": float(r.adx),
            })
        except Exception as e:
            rows.append({"Coin": symbol, "Prijs": np.nan, "Score": 0, "LONG": 0, "SHORT": 0, "Signaal": "⚠️ FOUT", "RSI": np.nan, "ADX": np.nan})

scan = pd.DataFrame(rows).sort_values(["Score", "Coin"], ascending=[False, True])
st.dataframe(scan, hide_index=True, use_container_width=True)

valid = scan[scan["Signaal"] != "⚠️ FOUT"]
if len(valid):
    best = valid.iloc[0]
    st.subheader("🏆 Beste setup")
    a,b,c,d = st.columns(4)
    a.metric("Coin", best["Coin"])
    b.metric("Score", f'{int(best["Score"])}/100')
    c.metric("Signaal", best["Signaal"])
    d.metric("RSI", f'{best["RSI"]:.1f}')

    best_symbol = best["Coin"]
    best_df = indicators(get_klines(best_symbol, interval, min(candles_count, 2000)))
    last = best_df.iloc[-1]
    analysis = analyse(last, mode)
    plan = trade_plan(last, analysis["signal"], capital, risk_pct, mode)

    if plan:
        st.subheader("🎯 Trade-plan")
        a,b,c,d = st.columns(4)
        a.metric("Entry", f"${plan['entry']:,.4f}")
        b.metric("Stop-loss", f"${plan['stop']:,.4f}")
        c.metric("TP1", f"${plan['tp1']:,.4f}")
        d.metric("TP2", f"${plan['tp2']:,.4f}")
        a,b,c,d = st.columns(4)
        a.metric("Positie", f"{plan['qty']:.6f}")
        b.metric("Risico", f"€{plan['risk_cash']:.2f}")
        c.metric("Notional", f"€{plan['notional']:.2f}")
        d.metric("Risk/Reward", f"1:{plan['rr']:.1f}")

        reason_list = analysis["long_reasons"] if analysis["signal"] == "LONG" else analysis["short_reasons"]
        st.write("**Bevestigingen:** " + (" • ".join(reason_list) if reason_list else "geen"))

        if st.button(f"🧪 Open paper trade — {best_symbol} {analysis['signal']}"):
            st.success(execute_paper(plan, best_symbol, analysis["signal"]))
            st.rerun()

    # Candlestick chart
    st.subheader(f"📈 {best_symbol} — {interval}")
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=best_df.time,
        open=best_df.open, high=best_df.high,
        low=best_df.low, close=best_df.close,
        name="Prijs"
    ))
    fig.add_trace(go.Scatter(x=best_df.time, y=best_df.ema21, name="EMA21"))
    fig.add_trace(go.Scatter(x=best_df.time, y=best_df.ema50, name="EMA50"))
    fig.update_layout(
        height=500, margin=dict(l=10,r=10,t=20,b=10),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h")
    )
    st.plotly_chart(fig, use_container_width=True)

    # Indicator overview
    st.subheader("📊 Indicatoren")
    a,b,c,d = st.columns(4)
    a.metric("RSI", f"{last.rsi:.1f}")
    b.metric("ADX", f"{last.adx:.1f}")
    c.metric("ATR", f"{last.atr_pct:.2f}%")
    d.metric("MACD", "Bullish" if last.macd > last.macd_signal else "Bearish")

# Paper trading
st.divider()
st.subheader("🧪 Paper Trading")
p = st.session_state.paper_position
if p:
    a,b,c,d = st.columns(4)
    a.metric("Positie", f"{p['symbol']} {p['side']}")
    a.metric("Entry", f"${p['entry']:,.4f}")
    a.metric("Stop", f"${p['stop']:,.4f}")
    a.metric("TP2", f"${p['tp2']:,.4f}")
    try:
        current = float(indicators(get_klines(p["symbol"], interval, 100)).iloc[-1].close)
        pnl = (current-p["entry"])*p["qty"] if p["side"]=="LONG" else (p["entry"]-current)*p["qty"]
        st.metric("Open P&L", f"€{pnl:,.2f}")
        if st.button("❌ Sluit paper trade"):
            close_paper(current)
            st.success("Paper trade gesloten.")
            st.rerun()
    except Exception as e:
        st.warning(f"Live P&L niet beschikbaar: {e}")
else:
    st.info("Geen open paper trade.")

if st.session_state.paper_trades:
    st.dataframe(pd.DataFrame(st.session_state.paper_trades), hide_index=True, use_container_width=True)

# Backtest
st.divider()
st.subheader("🧪 Backtest")
bt_symbol = st.selectbox("Backtest coin", coins)
if st.button("▶️ Start backtest"):
    try:
        bt_df = get_klines(bt_symbol, interval, candles_count)
        result = backtest(bt_df, mode, capital, risk_pct)
        a,b,c,d = st.columns(4)
        a.metric("Eindkapitaal", f"€{result['final']:,.2f}")
        b.metric("Rendement", f"{result['return_pct']:.2f}%")
        c.metric("Winrate", f"{result['winrate']:.1f}%")
        d.metric("Max drawdown", f"{result['max_drawdown']:.2f}%")
        st.metric("Profit factor", f"{result['profit_factor']:.2f}" if np.isfinite(result["profit_factor"]) else "∞")
        st.write(f"**Trades:** {len(result['trades'])}")
        if len(result["trades"]):
            st.dataframe(result["trades"].tail(50), hide_index=True, use_container_width=True)
        else:
            st.info("Geen trades met deze instellingen in de gekozen periode.")
    except Exception as e:
        st.error(f"Backtest mislukt: {e}")

st.caption("Paper trading only. Geen echte orders of financieel advies. Historische resultaten voorspellen toekomstige resultaten niet.")
