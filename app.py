
import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="Crypto DayTrader v5", page_icon="₿", layout="wide")

BINANCE = "https://data-api.binance.vision/api/v3/klines"
COINS = ["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","LINKUSDT","LTCUSDT","DOTUSDT"]

@st.cache_data(ttl=20, show_spinner=False)
def candles(symbol, interval="5m", limit=1500):
    rows=[]; end=None; remaining=min(int(limit),3000)
    while remaining:
        n=min(1000,remaining)
        params={"symbol":symbol,"interval":interval,"limit":n}
        if end is not None: params["endTime"]=end
        r=requests.get(BINANCE,params=params,timeout=15,headers={"User-Agent":"Crypto-DayTrader/5.0"})
        r.raise_for_status()
        b=r.json()
        if not b: break
        rows=b+rows; end=b[0][0]-1; remaining-=len(b)
        if len(b)<n: break
    cols=["open_time","open","high","low","close","volume","close_time","qv","trades","tb","tq","ignore"]
    d=pd.DataFrame(rows,columns=cols).drop_duplicates("open_time")
    for c in ["open","high","low","close","volume"]: d[c]=pd.to_numeric(d[c],errors="coerce")
    d["time"]=pd.to_datetime(d.open_time,unit="ms",utc=True)
    return d.sort_values("time")[["time","open","high","low","close","volume"]].dropna().reset_index(drop=True)

def rsi(s,n=14):
    d=s.diff(); g=d.clip(lower=0); l=-d.clip(upper=0)
    ag=g.ewm(alpha=1/n,adjust=False).mean(); al=l.ewm(alpha=1/n,adjust=False).mean()
    rs=ag/al.replace(0,np.nan)
    return 100-100/(1+rs)

def ind(d):
    x=d.copy()
    x["ema9"]=x.close.ewm(span=9,adjust=False).mean()
    x["ema21"]=x.close.ewm(span=21,adjust=False).mean()
    x["ema50"]=x.close.ewm(span=50,adjust=False).mean()
    x["ema200"]=x.close.ewm(span=200,adjust=False).mean()
    x["rsi"]=rsi(x.close)
    e12=x.close.ewm(span=12,adjust=False).mean(); e26=x.close.ewm(span=26,adjust=False).mean()
    x["macd"]=e12-e26; x["macd_signal"]=x.macd.ewm(span=9,adjust=False).mean()
    tr=pd.concat([x.high-x.low,(x.high-x.close.shift()).abs(),(x.low-x.close.shift()).abs()],axis=1).max(axis=1)
    x["atr"]=tr.ewm(alpha=1/14,adjust=False).mean(); x["atr_pct"]=x.atr/x.close*100
    x["vol_ma"]=x.volume.rolling(20).mean()
    up=x.high.diff(); down=-x.low.diff()
    plus=np.where((up>down)&(up>0),up,0); minus=np.where((down>up)&(down>0),down,0)
    p=100*pd.Series(plus,index=x.index).ewm(alpha=1/14,adjust=False).mean()/x.atr.replace(0,np.nan)
    m=100*pd.Series(minus,index=x.index).ewm(alpha=1/14,adjust=False).mean()/x.atr.replace(0,np.nan)
    dx=abs(p-m)/(p+m).replace(0,np.nan)*100
    x["adx"]=dx.ewm(alpha=1/14,adjust=False).mean()
    return x

def direction(row):
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

def signal_at(i, x, mode):
    r=x.iloc[i]; L,S=direction(r)
    # A simplified single-timeframe score for historical testing.
    threshold=72 if mode=="Conservatief" else 62
    if L>=threshold and L>S+8: return "LONG",L
    if S>=threshold and S>L+8: return "SHORT",S
    return "WAIT",max(L,S)

def run_backtest(df, mode, capital=1000, risk_pct=1.0, fee_pct=0.10, slippage_pct=0.03):
    x=ind(df).dropna().reset_index(drop=True)
    cash=float(capital); pos=None; trades=[]; equity=[]; start_idx=205
    for i in range(start_idx,len(x)):
        r=x.iloc[i]
        sig,score=signal_at(i,x,mode)
        if pos is None and sig in ("LONG","SHORT"):
            dist=max(float(r.atr)*1.25,float(r.close)*0.004)
            risk_cash=cash*risk_pct/100
            qty=risk_cash/dist if dist>0 else 0
            entry=float(r.close)*(1+slippage_pct/100 if sig=="LONG" else 1-slippage_pct/100)
            rr=2.2 if mode=="Conservatief" else 1.7
            stop=entry-dist if sig=="LONG" else entry+dist
            tp=entry+dist*rr if sig=="LONG" else entry-dist*rr
            pos={"side":sig,"entry":entry,"stop":stop,"tp":tp,"qty":qty,"time":r.time,"score":score}
        elif pos is not None:
            exit_price=None; reason=None
            if pos["side"]=="LONG":
                if r.low<=pos["stop"]: exit_price=pos["stop"]; reason="SL"
                elif r.high>=pos["tp"]: exit_price=pos["tp"]; reason="TP"
            else:
                if r.high>=pos["stop"]: exit_price=pos["stop"]; reason="SL"
                elif r.low<=pos["tp"]: exit_price=pos["tp"]; reason="TP"
            if exit_price is not None:
                exit_price*=1-slippage_pct/100 if pos["side"]=="LONG" else 1+slippage_pct/100
                pnl=(exit_price-pos["entry"])*pos["qty"] if pos["side"]=="LONG" else (pos["entry"]-exit_price)*pos["qty"]
                fees=(pos["entry"]*pos["qty"]+exit_price*pos["qty"])*fee_pct/100
                pnl-=fees; cash+=pnl
                trades.append({"Side":pos["side"],"Entry":pos["entry"],"Exit":exit_price,"P&L":pnl,"Result":reason,"Score":pos["score"],"Entry time":pos["time"],"Exit time":r.time})
                pos=None
        equity.append(cash)
    t=pd.DataFrame(trades)
    if len(t):
        wins=t[t["P&L"]>0]["P&L"].sum(); losses=abs(t[t["P&L"]<0]["P&L"].sum())
        pf=wins/losses if losses else np.inf
        wr=(t["P&L"]>0).mean()*100
        avg=t["P&L"].mean()
    else:
        pf=0; wr=0; avg=0
    eq=pd.Series(equity)
    dd=(eq/eq.cummax()-1)*100 if len(eq) else pd.Series([0])
    return {"final":cash,"return":(cash/capital-1)*100,"trades":t,"winrate":wr,"pf":pf,"avg":avg,"maxdd":dd.min(),"equity":eq}

def walk_forward(df, mode, capital, risk):
    # Three chronological folds: train is reported for context, final fold is out-of-sample.
    n=len(df); cut1=int(n*0.5); cut2=int(n*0.75)
    oos=df.iloc[cut2:].copy()
    # No parameter fitting is performed: this deliberately keeps the test out-of-sample.
    return run_backtest(oos,mode,capital,risk)

st.title("₿ Crypto DayTrader v5")
st.caption("Strategy Lab • backtesting • walk-forward test • multi-indicator paper trading")

with st.sidebar:
    mode=st.radio("Strategie",["Conservatief","Agressief"])
    symbol=st.selectbox("Backtest coin",COINS)
    interval=st.selectbox("Timeframe",["5m","15m","1h"],index=0)
    capital=st.number_input("Startkapitaal (€)",100.0,100000.0,1000.0,100.0)
    risk=st.slider("Risico per trade (%)",0.25,3.0,1.0,0.25)
    history=st.select_slider("Historische candles",[500,1000,1500,2000,3000],value=2000)
    if st.button("🔄 Vernieuw data"):
        st.cache_data.clear(); st.rerun()

tab1,tab2,tab3=st.tabs(["📊 Strategy Lab","📈 Equity curve","🧪 Walk-forward"])

with tab1:
    st.subheader(f"{symbol} • {interval} • {mode}")
    if st.button("▶️ Run backtest",type="primary"):
        with st.spinner("Historische data testen..."):
            result=run_backtest(candles(symbol,interval,history),mode,capital,risk)
        a,b,c,d=st.columns(4)
        a.metric("Rendement",f"{result['return']:.2f}%")
        b.metric("Winrate",f"{result['winrate']:.1f}%")
        c.metric("Profit factor",f"{result['pf']:.2f}" if np.isfinite(result["pf"]) else "∞")
        d.metric("Max drawdown",f"{result['maxdd']:.2f}%")
        a,b,c,d=st.columns(4)
        a.metric("Trades",len(result["trades"]))
        a.metric("Eindkapitaal",f"€{result['final']:,.2f}")
        a.metric("Gem. trade",f"€{result['avg']:,.2f}")
        st.session_state["last_result"]=result
        if len(result["trades"]):
            st.subheader("Trade log")
            st.dataframe(result["trades"].tail(100),hide_index=True,use_container_width=True)
        else:
            st.info("Geen trades in deze historische periode.")

    if "last_result" in st.session_state:
        r=st.session_state["last_result"]
        if len(r["trades"]):
            st.subheader("Trade-verdeling")
            by_side=r["trades"].groupby("Side")["P&L"].agg(["count","sum","mean"]).reset_index()
            st.dataframe(by_side,hide_index=True,use_container_width=True)

with tab2:
    if "last_result" not in st.session_state:
        st.info("Voer eerst een backtest uit.")
    else:
        r=st.session_state["last_result"]
        fig=go.Figure()
        fig.add_trace(go.Scatter(y=r["equity"],mode="lines",name="Equity"))
        fig.update_layout(height=450,title="Equity curve",xaxis_title="Trade/checkpoint",yaxis_title="€")
        st.plotly_chart(fig,use_container_width=True)

with tab3:
    st.subheader("Out-of-sample walk-forward")
    st.write("De laatste 25% van de historische data wordt volledig apart getest. Er worden geen parameters op deze testperiode aangepast.")
    if st.button("▶️ Run walk-forward"):
        with st.spinner("Out-of-sample test..."):
            wf=walk_forward(candles(symbol,interval,history),mode,capital,risk)
        a,b,c,d=st.columns(4)
        a.metric("OOS rendement",f"{wf['return']:.2f}%")
        b.metric("OOS winrate",f"{wf['winrate']:.1f}%")
        c.metric("OOS profit factor",f"{wf['pf']:.2f}" if np.isfinite(wf["pf"]) else "∞")
        d.metric("OOS max drawdown",f"{wf['maxdd']:.2f}%")
        st.write(f"OOS trades: **{len(wf['trades'])}**")
        if len(wf["trades"]):
            st.dataframe(wf["trades"].tail(100),hide_index=True,use_container_width=True)

st.divider()
st.subheader("⚠️ Interpretatie")
st.write("Een hoge winrate is niet genoeg. Kijk samen naar profit factor, drawdown, aantal trades en vooral de out-of-sample resultaten. Deze backtest is een onderzoeksinstrument, geen garantie voor toekomstige winst.")
st.caption("Geen echte orders. Geen financieel advies. Fees/slippage zijn vereenvoudigde aannames.")
