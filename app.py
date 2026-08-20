import requests
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Crypto DayTrader v3", page_icon="₿", layout="wide")

BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"
TIMEFRAMES = {"1m":"1m","3m":"3m","5m":"5m","15m":"15m","30m":"30m","1h":"1h"}

@st.cache_data(ttl=20)
def get_klines(symbol, interval, limit=300):
    r = requests.get(
        BINANCE_URL,
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or not data:
        raise ValueError("Geen marktdata beschikbaar.")
    cols = ["open_time","open","high","low","close","volume","close_time",
            "quote_volume","trades","taker_buy_base","taker_buy_quote","ignore"]
    df = pd.DataFrame(data, columns=cols)
    for c in ["open","high","low","close","volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df[["time","open","high","low","close","volume"]].dropna()

def rsi(s, n=14):
    d = s.diff()
    gain = d.clip(lower=0)
    loss = -d.clip(upper=0)
    ag = gain.ewm(alpha=1/n, adjust=False).mean()
    al = loss.ewm(alpha=1/n, adjust=False).mean()
    rs = ag / al.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def indicators(df):
    x = df.copy()
    x["ema9"] = x.close.ewm(span=9, adjust=False).mean()
    x["ema21"] = x.close.ewm(span=21, adjust=False).mean()
    x["ema50"] = x.close.ewm(span=50, adjust=False).mean()
    x["rsi"] = rsi(x.close)
    e12 = x.close.ewm(span=12, adjust=False).mean()
    e26 = x.close.ewm(span=26, adjust=False).mean()
    x["macd"] = e12 - e26
    x["macd_signal"] = x.macd.ewm(span=9, adjust=False).mean()
    x["vol_ma"] = x.volume.rolling(20).mean()
    tr = pd.concat([
        x.high-x.low,
        (x.high-x.close.shift()).abs(),
        (x.low-x.close.shift()).abs()
    ], axis=1).max(axis=1)
    x["atr"] = tr.rolling(14).mean()
    return x

def analyse(row, mode):
    score = 0
    reasons = []
    if row.ema9 > row.ema21:
        score += 2; reasons.append("EMA trend bullish")
    if row.close > row.ema50:
        score += 2; reasons.append("boven EMA50")
    if row.macd > row.macd_signal:
        score += 2; reasons.append("MACD bullish")
    if 45 <= row.rsi <= 68:
        score += 2; reasons.append("RSI gunstig")
    elif row.rsi < 35:
        score += 1; reasons.append("RSI oversold")
    if pd.notna(row.vol_ma) and row.volume > row.vol_ma:
        score += 1; reasons.append("volume sterk")

    threshold = 7 if mode == "Conservatief" else 5
    signal = "🟢 LONG" if score >= threshold else "🟡 WACHTEN"
    return score, signal, reasons

st.title("₿ Crypto DayTrader v3")
st.caption("Mobiele scanner • paper trading • signalen zijn geen financieel advies.")

with st.sidebar:
    st.header("Instellingen")
    mode = st.radio("Strategie", ["Conservatief", "Agressief"])
    interval = st.selectbox("Timeframe", list(TIMEFRAMES), index=2)
    capital = st.number_input("Kapitaal (€)", 100.0, 100000.0, 1000.0, 100.0)
    risk = st.slider("Risico per trade (%)", 0.25, 3.0, 1.0, 0.25)
    symbols_text = st.text_area(
        "Coins scannen",
        "BTCUSDT\nETHUSDT\nSOLUSDT\nXRPUSDT\nDOGEUSDT\nADAUSDT\nAVAXUSDT\nLINKUSDT\nLTCUSDT\nDOTUSDT"
    )
    if st.button("🔄 Nieuwe scan"):
        st.cache_data.clear()
        st.rerun()

symbols = [s.strip().upper().replace("/", "") for s in symbols_text.splitlines() if s.strip()]
results = []

with st.spinner("Crypto's worden gescand..."):
    for symbol in symbols:
        try:
            df = indicators(get_klines(symbol, interval))
            row = df.iloc[-1]
            score, signal, reasons = analyse(row, mode)
            results.append({
                "Coin": symbol,
                "Prijs": row.close,
                "Score": score,
                "Signaal": signal,
                "RSI": row.rsi,
                "Reden": " • ".join(reasons) if reasons else "Geen sterke bevestiging"
            })
        except Exception as e:
            results.append({
                "Coin": symbol, "Prijs": np.nan, "Score": 0,
                "Signaal": "⚠️ FOUT", "RSI": np.nan, "Reden": str(e)
            })

res = pd.DataFrame(results).sort_values(["Score","Coin"], ascending=[False, True])

st.subheader(f"🔎 Markt Scanner — {mode}")
st.dataframe(
    res[["Coin","Prijs","Score","Signaal","RSI","Reden"]],
    hide_index=True,
    use_container_width=True
)

valid = res[res["Signaal"] != "⚠️ FOUT"]
if len(valid):
    best = valid.iloc[0]
    st.subheader("🏆 Beste kans")
    a,b,c,d = st.columns(4)
    a.metric("Coin", best.Coin)
    b.metric("Score", f"{int(best.Score)}/9")
    c.metric("Signaal", best.Signaal)
    d.metric("RSI", f"{best.RSI:.1f}")

    try:
        best_df = indicators(get_klines(best.Coin, interval))
        last = best_df.iloc[-1]
        stop_dist = max(last.atr * 1.2, last.close * 0.004)
        entry = last.close
        stop = entry - stop_dist
        rr = 2.0 if mode == "Conservatief" else 1.6
        target = entry + stop_dist * rr
        risk_cash = capital * risk / 100
        qty = risk_cash / (entry - stop) if entry > stop else 0

        st.subheader("🎯 Trade-plan")
        a,b,c,d = st.columns(4)
        a.metric("Entry", f"${entry:,.2f}")
        b.metric("Stop-loss", f"${stop:,.2f}")
        c.metric("Take-profit", f"${target:,.2f}")
        d.metric("Positie", f"{qty:.6f}")
        st.caption(f"Risico: €{risk_cash:.2f} • Risk/Reward: 1:{rr}")

        st.subheader(f"📈 {best.Coin}")
        st.line_chart(best_df.set_index("time")[["close","ema9","ema21","ema50"]])
    except Exception as e:
        st.error(f"Trade-plan kon niet worden berekend: {e}")

st.divider()
st.caption("Paper trading only. Geen echte orders. Backtests en signalen zijn geen garantie voor toekomstige resultaten.")
