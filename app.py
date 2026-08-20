
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(
    page_title="Crypto DayTrader v4",
    page_icon="₿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

BINANCE = "https://data-api.binance.vision/api/v3/klines"
DEFAULT_COINS = [
    "BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT",
    "ADAUSDT","AVAXUSDT","LINKUSDT","LTCUSDT","DOTUSDT"
]
TF_SECONDS = {"5m":300,"15m":900,"1h":3600}

@st.cache_data(ttl=20, show_spinner=False)
def get_klines(symbol, interval, limit=500):
    rows=[]
    end_time=None
    remaining=min(int(limit),3000)
    while remaining>0:
        n=min(1000,remaining)
        params={"symbol":symbol,"interval":interval,"limit":n}
        if end_time is not None:
            params["endTime"]=end_time
        r=requests.get(BINANCE,params=params,timeout=15,headers={"User-Agent":"Crypto-DayTrader/4.0"})
        r.raise_for_status()
        batch=r.json()
        if not batch: break
        rows=batch+rows
        end_time=batch[0][0]-1
        remaining-=len(batch)
        if len(batch)<n: break
    if not rows: raise ValueError("Geen marktdata ontvangen.")
    cols=["open_time","open","high","low","close","volume","close_time","quote_volume","trades","taker_buy_base","taker_buy_quote","ignore"]
    df=pd.DataFrame(rows,columns=cols).drop_duplicates("open_time")
    for c in ["open","high","low","close","volume"]:
        df[c]=pd.to_numeric(df[c],errors="coerce")
    df["time"]=pd.to_datetime(df["open_time"],unit="ms",utc=True)
    return df.sort_values("time").tail(limit)[["time","open","high","low","close","volume"]].dropna().reset_index(drop=True)

def rsi(s,n=14):
    d=s.diff()
    g=d.clip(lower=0)
    l=-d.clip(upper=0)
    ag=g.ewm(alpha=1/n,adjust=False).mean()
    al=l.ewm(alpha=1/n,adjust=False).mean()
    rs=ag/al.replace(0,np.nan)
    return 100-(100/(1+rs))

def indicators(df):
    x=df.copy()
    x["ema9"]=x.close.ewm(span=9,adjust=False).mean()
    x["ema21"]=x.close.ewm(span=21,adjust=False).mean()
    x["ema50"]=x.close.ewm(span=50,adjust=False).mean()
    x["ema200"]=x.close.ewm(span=200,adjust=False).mean()
    x["rsi"]=rsi(x.close)
    e12=x.close.ewm(span=12,adjust=False).mean()
    e26=x.close.ewm(span=26,adjust=False).mean()
    x["macd"]=e12-e26
    x["macd_signal"]=x.macd.ewm(span=9,adjust=False).mean()
    tr=pd.concat([x.high-x.low,(x.high-x.close.shift()).abs(),(x.low-x.close.shift()).abs()],axis=1).max(axis=1)
    x["atr"]=tr.ewm(alpha=1/14,adjust=False).mean()
    x["atr_pct"]=x.atr/x.close*100
    x["vol_ma"]=x.volume.rolling(20).mean()
    up=x.high.diff(); down=-x.low.diff()
    plus=np.where((up>down)&(up>0),up,0.0)
    minus=np.where((down>up)&(down>0),down,0.0)
    a=x["atr"].replace(0,np.nan)
    p=100*pd.Series(plus,index=x.index).ewm(alpha=1/14,adjust=False).mean()/a
    m=100*pd.Series(minus,index=x.index).ewm(alpha=1/14,adjust=False).mean()/a
    dx=(abs(p-m)/(p+m).replace(0,np.nan))*100
    x["adx"]=dx.ewm(alpha=1/14,adjust=False).mean()
    return x

def timeframe_score(row):
    long=short=0
    if row.ema9>row.ema21: long+=15
    elif row.ema9<row.ema21: short+=15
    if row.close>row.ema50: long+=10
    elif row.close<row.ema50: short+=10
    if row.close>row.ema200: long+=10
    elif row.close<row.ema200: short+=10
    if row.macd>row.macd_signal: long+=15
    elif row.macd<row.macd_signal: short+=15
    if 50<=row.rsi<=68: long+=10
    elif 32<=row.rsi<=50: short+=10
    if row.adx>=20:
        if row.ema9>row.ema21: long+=10
        elif row.ema9<row.ema21: short+=10
    if pd.notna(row.vol_ma) and row.volume>row.vol_ma*1.15:
        if row.close>=row.open: long+=10
        else: short+=10
    if 0.15<=row.atr_pct<=4: long+=5; short+=5
    return min(long,100),min(short,100)

def multi_tf_analysis(symbol, mode):
    data={}
    for tf in ["1h","15m","5m"]:
        d=indicators(get_klines(symbol,tf,500))
        data[tf]=d
    scores={tf:timeframe_score(data[tf].iloc[-1]) for tf in data}
    weights={"1h":0.45,"15m":0.35,"5m":0.20}
    long_total=sum(scores[tf][0]*weights[tf] for tf in scores)
    short_total=sum(scores[tf][1]*weights[tf] for tf in scores)
    # Normalize directional score to 0-100 using the weighted maximum.
    threshold=72 if mode=="Conservatief" else 62
    if long_total>=threshold and long_total>short_total+8:
        signal="LONG"
        score=long_total
    elif short_total>=threshold and short_total>long_total+8:
        signal="SHORT"
        score=short_total
    else:
        signal="WAIT"
        score=max(long_total,short_total)
    alignment = (
        ("1H " + ("↑" if scores["1h"][0]>scores["1h"][1] else "↓")) +
        " · 15M " + ("↑" if scores["15m"][0]>scores["15m"][1] else "↓") +
        " · 5M " + ("↑" if scores["5m"][0]>scores["5m"][1] else "↓")
    )
    return data,scores,long_total,short_total,score,signal,alignment

def plan(row,signal,capital,risk_pct,mode):
    if signal not in ("LONG","SHORT"): return None
    entry=float(row.close)
    dist=max(float(row.atr)*1.25,entry*0.004)
    rr=2.2 if mode=="Conservatief" else 1.7
    risk_cash=capital*risk_pct/100
    qty=risk_cash/dist if dist>0 else 0
    if signal=="LONG":
        stop=entry-dist; tp1=entry+dist; tp2=entry+dist*rr
    else:
        stop=entry+dist; tp1=entry-dist; tp2=entry-dist*rr
    return dict(entry=entry,stop=stop,tp1=tp1,tp2=tp2,qty=qty,risk=risk_cash,rr=rr,notional=qty*entry)

def init_state():
    st.session_state.setdefault("paper_cash",1000.0)
    st.session_state.setdefault("paper_position",None)
    st.session_state.setdefault("paper_trades",[])
init_state()

with st.sidebar:
    st.header("⚙️ Instellingen")
    mode=st.radio("Strategie",["Conservatief","Agressief"])
    capital=st.number_input("Analyse-kapitaal (€)",100.0,100000.0,1000.0,100.0)
    risk_pct=st.slider("Risico per trade (%)",0.25,3.0,1.0,0.25)
    coins_text=st.text_area("Coins", "\n".join(DEFAULT_COINS))
    if st.button("🔄 Vernieuw"):
        st.cache_data.clear(); st.rerun()

coins=[x.strip().upper().replace("/","") for x in coins_text.splitlines() if x.strip()]

st.title("₿ Crypto DayTrader v4")
st.caption("Multi-timeframe scanner • 1H → 15M → 5M • paper trading • geen financieel advies")

rows=[]
with st.spinner("1H, 15M en 5M worden gecontroleerd..."):
    for symbol in coins:
        try:
            data,scores,lt,stotal,score,signal,alignment=multi_tf_analysis(symbol,mode)
            r=data["5m"].iloc[-1]
            rows.append({
                "Coin":symbol,"Signaal":"🟢 LONG" if signal=="LONG" else ("🔴 SHORT" if signal=="SHORT" else "🟡 WACHTEN"),
                "Score":round(score), "1H":round(max(scores["1h"])), "15M":round(max(scores["15m"])),
                "5M":round(max(scores["5m"])),"Prijs":float(r.close),"RSI":float(r.rsi),
                "Trend":alignment
            })
        except Exception as e:
            rows.append({"Coin":symbol,"Signaal":"⚠️ FOUT","Score":0,"1H":0,"15M":0,"5M":0,"Prijs":np.nan,"RSI":np.nan,"Trend":str(e)})

scan=pd.DataFrame(rows).sort_values(["Score","Coin"],ascending=[False,True])
st.subheader("🔎 Multi-timeframe scanner")
st.dataframe(scan,hide_index=True,use_container_width=True)

valid=scan[scan["Signaal"]!="⚠️ FOUT"]
if len(valid):
    best=valid.iloc[0]
    st.subheader("🏆 Beste setup")
    a,b,c,d=st.columns(4)
    a.metric("Coin",best.Coin)
    b.metric("Score",f'{int(best.Score)}/100')
    c.metric("Signaal",best.Signaal)
    d.metric("Timeframes",best.Trend)

    symbol=best.Coin
    data,scores,lt,stotal,score,signal,alignment=multi_tf_analysis(symbol,mode)
    last=data["5m"].iloc[-1]
    p=plan(last,signal,capital,risk_pct,mode)

    if p:
        st.subheader("🎯 Trade-plan")
        a,b,c,d=st.columns(4)
        a.metric("Entry",f"${p['entry']:,.4f}")
        b.metric("Stop-loss",f"${p['stop']:,.4f}")
        c.metric("TP1",f"${p['tp1']:,.4f}")
        d.metric("TP2",f"${p['tp2']:,.4f}")
        a,b,c,d=st.columns(4)
        a.metric("Positie",f"{p['qty']:.6f}")
        b.metric("Risico",f"€{p['risk']:.2f}")
        c.metric("Notional",f"€{p['notional']:.2f}")
        d.metric("R/R",f"1:{p['rr']:.1f}")

    st.subheader(f"📈 {symbol} — 5M")
    d5=data["5m"].tail(200)
    fig=go.Figure()
    fig.add_trace(go.Candlestick(x=d5.time,open=d5.open,high=d5.high,low=d5.low,close=d5.close,name="Prijs"))
    fig.add_trace(go.Scatter(x=d5.time,y=d5.ema21,name="EMA21"))
    fig.add_trace(go.Scatter(x=d5.time,y=d5.ema50,name="EMA50"))
    if p:
        fig.add_hline(y=p["entry"],annotation_text="Entry")
        fig.add_hline(y=p["stop"],annotation_text="SL")
        fig.add_hline(y=p["tp1"],annotation_text="TP1")
        fig.add_hline(y=p["tp2"],annotation_text="TP2")
    fig.update_layout(height=500,margin=dict(l=5,r=5,t=15,b=5),xaxis_rangeslider_visible=False)
    st.plotly_chart(fig,use_container_width=True)

    st.subheader("📊 Multi-timeframe details")
    detail=pd.DataFrame([
        ["1H",scores["1h"][0],scores["1h"][1]],
        ["15M",scores["15m"][0],scores["15m"][1]],
        ["5M",scores["5m"][0],scores["5m"][1]],
    ],columns=["Timeframe","LONG score","SHORT score"])
    st.dataframe(detail,hide_index=True,use_container_width=True)

# Paper trading
st.divider()
st.subheader("🧪 Paper Trading")
pstate=st.session_state.paper_position
if pstate:
    a,b,c,d=st.columns(4)
    a.metric("Positie",f"{pstate['symbol']} {pstate['side']}")
    a.metric("Entry",f"${pstate['entry']:,.4f}")
    a.metric("SL",f"${pstate['stop']:,.4f}")
    a.metric("TP2",f"${pstate['tp2']:,.4f}")
else:
    st.info("Geen open paper trade. Paper trading blijft lokaal in deze sessie.")

st.caption("Gebruik LONG/SHORT signalen niet als automatisch koop- of verkoopadvies. Eerst testen met paper trading.")
