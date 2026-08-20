
import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="Crypto DayTrader v6", page_icon="₿", layout="wide")

BINANCE = "https://data-api.binance.vision/api/v3/klines"
COINS = ["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","LINKUSDT","LTCUSDT","DOTUSDT"]

@st.cache_data(ttl=30, show_spinner=False)
def candles(symbol, interval, limit=1500):
    rows=[]; end=None; remaining=min(int(limit),3000)
    while remaining:
        n=min(1000,remaining)
        p={"symbol":symbol,"interval":interval,"limit":n}
        if end is not None: p["endTime"]=end
        r=requests.get(BINANCE,params=p,timeout=15,headers={"User-Agent":"Crypto-DayTrader/6.0"})
        r.raise_for_status(); b=r.json()
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
    return 100-100/(1+(ag/al.replace(0,np.nan)))

def indicators(d):
    x=d.copy()
    x["ema9"]=x.close.ewm(span=9,adjust=False).mean()
    x["ema21"]=x.close.ewm(span=21,adjust=False).mean()
    x["ema50"]=x.close.ewm(span=50,adjust=False).mean()
    x["ema200"]=x.close.ewm(span=200,adjust=False).mean()
    x["rsi"]=rsi(x.close)
    e12=x.close.ewm(span=12,adjust=False).mean(); e26=x.close.ewm(span=26,adjust=False).mean()
    x["macd"]=e12-e26; x["macd_signal"]=x.macd.ewm(span=9,adjust=False).mean()
    tr=pd.concat([x.high-x.low,(x.high-x.close.shift()).abs(),(x.low-x.close.shift()).abs()],axis=1).max(axis=1)
    x["atr"]=tr.ewm(alpha=1/14,adjust=False).mean()
    x["atr_pct"]=x.atr/x.close*100
    x["vol_ma"]=x.volume.rolling(20).mean()
    up=x.high.diff(); dn=-x.low.diff()
    plus=np.where((up>dn)&(up>0),up,0); minus=np.where((dn>up)&(dn>0),dn,0)
    p=100*pd.Series(plus,index=x.index).ewm(alpha=1/14,adjust=False).mean()/x.atr.replace(0,np.nan)
    m=100*pd.Series(minus,index=x.index).ewm(alpha=1/14,adjust=False).mean()/x.atr.replace(0,np.nan)
    x["adx"]=(abs(p-m)/(p+m).replace(0,np.nan)*100).ewm(alpha=1/14,adjust=False).mean()
    return x

def score_row(r):
    L=S=0
    if r.ema9>r.ema21: L+=15
    elif r.ema9<r.ema21: S+=15
    if r.close>r.ema50: L+=10
    elif r.close<r.ema50: S+=10
    if r.close>r.ema200: L+=10
    elif r.close<r.ema200: S+=10
    if r.macd>r.macd_signal: L+=15
    elif r.macd<r.macd_signal: S+=15
    if 50<=r.rsi<=68: L+=10
    elif 32<=r.rsi<=50: S+=10
    if r.adx>=20:
        if r.ema9>r.ema21: L+=10
        elif r.ema9<r.ema21: S+=10
    if pd.notna(r.vol_ma) and r.volume>r.vol_ma*1.15:
        if r.close>=r.open: L+=10
        else: S+=10
    if 0.15<=r.atr_pct<=4: L+=5; S+=5
    return min(L,100),min(S,100)

@st.cache_data(ttl=30, show_spinner=False)
def build_mtf(symbol, limit5):
    d5=indicators(candles(symbol,"5m",limit5))
    d15=indicators(candles(symbol,"15m",min(1000,max(500,limit5//3+100))))
    d1=indicators(candles(symbol,"1h",min(1000,max(500,limit5//12+100))))
    # Only completed higher-timeframe candles may influence a 5m decision.
    for d in (d15,d1):
        d["L"],d["S"]=zip(*d.apply(score_row,axis=1))
        d["available"]=d.time
        d.drop(columns=["time"],inplace=True)
    # Shift one candle so the currently forming 15m/1h candle cannot leak into 5m.
    d15["available"]=pd.to_datetime(candles(symbol,"15m",min(1000,max(500,limit5//3+100))).time,utc=True).shift(-1)
    d1["available"]=pd.to_datetime(candles(symbol,"1h",min(1000,max(500,limit5//12+100))).time,utc=True).shift(-1)
    d15=d15.dropna(subset=["available"]).sort_values("available")
    d1=d1.dropna(subset=["available"]).sort_values("available")
    d5["L5"],d5["S5"]=zip(*d5.apply(score_row,axis=1))
    base=d5.sort_values("time")
    m15=d15[["available","L","S"]].rename(columns={"L":"L15","S":"S15"})
    m1=d1[["available","L","S"]].rename(columns={"L":"L1","S":"S1"})
    out=pd.merge_asof(base,m15,left_on="time",right_on="available",direction="backward")
    out=pd.merge_asof(out,m1,left_on="time",right_on="available",direction="backward")
    out=out.dropna(subset=["L15","S15","L1","S1"]).reset_index(drop=True)
    return out

def make_signal(r,mode):
    # Exact scanner logic: 1H 45%, 15M 35%, 5M 20%.
    w1,w15,w5=.45,.35,.20
    L=r.L1*w1+r.L15*w15+r.L5*w5
    S=r.S1*w1+r.S15*w15+r.S5*w5
    threshold=72 if mode=="Conservatief" else 62
    if L>=threshold and L>S+8: return "LONG",L
    if S>=threshold and S>L+8: return "SHORT",S
    return "WAIT",max(L,S)

def backtest(df,mode,capital=1000,risk_pct=1,fee_pct=.10,slip_pct=.03):
    cash=float(capital); pos=None; trades=[]; equity=[]
    for i in range(1,len(df)):
        r=df.iloc[i]
        # Exit positions using the current candle. If both SL and TP are touched,
        # assume SL first: conservative treatment of unknown intrabar order.
        if pos is not None:
            exit_price=None; reason=None
            if pos["side"]=="LONG":
                if r.low<=pos["stop"]: exit_price=pos["stop"]; reason="SL"
                elif r.high>=pos["tp"]: exit_price=pos["tp"]; reason="TP"
            else:
                if r.high>=pos["stop"]: exit_price=pos["stop"]; reason="SL"
                elif r.low<=pos["tp"]: exit_price=pos["tp"]; reason="TP"
            if exit_price is not None:
                exit_price*=1-slip_pct/100 if pos["side"]=="LONG" else 1+slip_pct/100
                gross=(exit_price-pos["entry"])*pos["qty"] if pos["side"]=="LONG" else (pos["entry"]-exit_price)*pos["qty"]
                fees=(pos["entry"]*pos["qty"]+exit_price*pos["qty"])*fee_pct/100
                pnl=gross-fees; cash+=pnl
                trades.append({**pos,"Exit":exit_price,"P&L":pnl,"Result":reason,"Exit time":r.time})
                pos=None
        # Entry happens at the close of the current candle and can only be
        # evaluated for the next candle, preventing same-candle hindsight.
        if pos is None:
            sig,score=make_signal(r,mode)
            if sig in ("LONG","SHORT") and np.isfinite(r.atr) and r.atr>0:
                dist=max(float(r.atr)*1.25,float(r.close)*.004)
                risk_cash=max(cash,0)*risk_pct/100
                qty=risk_cash/dist if dist else 0
                entry=float(r.close)*(1+slip_pct/100 if sig=="LONG" else 1-slip_pct/100)
                rr=2.2 if mode=="Conservatief" else 1.7
                stop=entry-dist if sig=="LONG" else entry+dist
                tp=entry+dist*rr if sig=="LONG" else entry-dist*rr
                pos={"side":sig,"entry":entry,"stop":stop,"tp":tp,"qty":qty,"Entry time":r.time,"Score":score}
        equity.append(cash)
    if pos is not None and len(df):
        r=df.iloc[-1]; exit_price=float(r.close)
        gross=(exit_price-pos["entry"])*pos["qty"] if pos["side"]=="LONG" else (pos["entry"]-exit_price)*pos["qty"]
        fees=(pos["entry"]*pos["qty"]+exit_price*pos["qty"])*fee_pct/100
        pnl=gross-fees; cash+=pnl
        trades.append({**pos,"Exit":exit_price,"P&L":pnl,"Result":"EOD","Exit time":r.time})
        equity.append(cash)
    t=pd.DataFrame(trades); eq=pd.Series(equity)
    wins=t.loc[t["P&L"]>0,"P&L"].sum() if len(t) else 0
    losses=abs(t.loc[t["P&L"]<0,"P&L"].sum()) if len(t) else 0
    pf=wins/losses if losses else (np.inf if wins else 0)
    wr=(t["P&L"]>0).mean()*100 if len(t) else 0
    dd=(eq/eq.cummax()-1)*100 if len(eq) else pd.Series([0])
    return {"final":cash,"return":(cash/capital-1)*100,"trades":t,"winrate":wr,"pf":pf,"dd":dd.min(),"equity":eq}

def result_row(symbol,mode,limit):
    try:
        d=build_mtf(symbol,limit)
        r=backtest(d,mode)
        return {"Coin":symbol,"Modus":mode,"Rendement %":r["return"],"Winrate %":r["winrate"],"Profit factor":r["pf"],"Max DD %":r["dd"],"Trades":len(r["trades"])}
    except Exception as e:
        return {"Coin":symbol,"Modus":mode,"Rendement %":np.nan,"Winrate %":np.nan,"Profit factor":np.nan,"Max DD %":np.nan,"Trades":0,"Fout":str(e)}

st.title("₿ Crypto DayTrader v6")
st.caption("Exact scanner logic • leak-free multi-timeframe backtest • optimizer • out-of-sample test")

with st.sidebar:
    symbol=st.selectbox("Coin",COINS)
    mode=st.radio("Strategie",["Conservatief","Agressief"])
    limit=st.select_slider("5M historie",[500,1000,1500,2000,3000],value=1500)
    capital=st.number_input("Startkapitaal (€)",100.0,100000.0,1000.0,100.0)
    risk=st.slider("Risico per trade (%)",.25,3.0,1.0,.25)
    fee=st.number_input("Fee per kant (%)",0.0,.50,.10,.01)
    slip=st.number_input("Slippage per kant (%)",0.0,.50,.03,.01)

t1,t2,t3=st.tabs(["🧪 Backtest","🏆 Optimizer","📉 Out-of-sample"])

with t1:
    st.subheader(f"{symbol} • 1H → 15M → 5M • {mode}")
    if st.button("▶️ Run exacte backtest",type="primary"):
        with st.spinner("1H/15M/5M synchroniseren en testen..."):
            d=build_mtf(symbol,limit); res=backtest(d,mode,capital,risk,fee,slip)
        st.session_state["v6res"]=res
        a,b,c,dv=st.columns(4)
        a.metric("Rendement",f"{res['return']:.2f}%")
        b.metric("Winrate",f"{res['winrate']:.1f}%")
        c.metric("Profit factor",f"{res['pf']:.2f}" if np.isfinite(res['pf']) else "∞")
        dv.metric("Max drawdown",f"{res['dd']:.2f}%")
        a,b,c,dv=st.columns(4)
        a.metric("Trades",len(res["trades"]))
        b.metric("Eindkapitaal",f"€{res['final']:,.2f}")
        c.metric("Winnende trades",int((res["trades"]["P&L"]>0).sum()) if len(res["trades"]) else 0)
        dvc= int((res["trades"]["P&L"]<0).sum()) if len(res["trades"]) else 0
        dv.metric("Verliezende trades",dvc)
        if len(res["trades"]): st.dataframe(res["trades"],hide_index=True,use_container_width=True)
    if "v6res" in st.session_state:
        r=st.session_state["v6res"]; fig=go.Figure(go.Scatter(y=r["equity"],mode="lines",name="Equity"))
        fig.update_layout(height=380,title="Equity curve",xaxis_title="Checkpoint",yaxis_title="€")
        st.plotly_chart(fig,use_container_width=True)

with t2:
    st.subheader("🏆 Coin & strategie optimizer")
    st.write("Test alle 10 coins met exact dezelfde 1H → 15M → 5M regels. Gebruik dit om kandidaten te vinden, niet om de beste historische score blind te kiezen.")
    if st.button("🚀 Test alle coins",type="primary"):
        results=[]
        with st.spinner("Dit kan even duren: meerdere coins en timeframes worden opgehaald..."):
            for m in ["Conservatief","Agressief"]:
                for s in COINS:
                    results.append(result_row(s,m,limit))
        opt=pd.DataFrame(results).sort_values(["Profit factor","Rendement %"],ascending=False)
        st.session_state["optimizer"]=opt
    if "optimizer" in st.session_state:
        opt=st.session_state["optimizer"]
        st.dataframe(opt.style.format({"Rendement %":"{:.2f}","Winrate %":"{:.1f}","Profit factor":"{:.2f}","Max DD %":"{:.2f}"}),use_container_width=True,hide_index=True)
        good=opt[(opt["Profit factor"]>=1.2)&(opt["Trades"]>=30)]
        if len(good): st.success(f"{len(good)} kandidaten voldoen voorlopig aan PF ≥ 1,20 en ≥ 30 trades.")
        else: st.warning("Geen kandidaat voldoet voorlopig aan PF ≥ 1,20 én ≥ 30 trades. Dat is nuttige informatie: de strategie heeft dan meer werk nodig.")

with t3:
    st.subheader("📉 Out-of-sample")
    st.write("De laatste 25% van de periode wordt apart getest. Er worden geen parameters op deze testperiode aangepast.")
    if st.button("▶️ Run OOS-test"):
        with st.spinner("Out-of-sample data testen..."):
            full=build_mtf(symbol,limit); cut=int(len(full)*.75)
            oos=backtest(full.iloc[cut:].reset_index(drop=True),mode,capital,risk,fee,slip)
        a,b,c,dv=st.columns(4)
        a.metric("OOS rendement",f"{oos['return']:.2f}%")
        b.metric("OOS winrate",f"{oos['winrate']:.1f}%")
        c.metric("OOS profit factor",f"{oos['pf']:.2f}" if np.isfinite(oos['pf']) else "∞")
        dv.metric("OOS max DD",f"{oos['dd']:.2f}%")
        st.write(f"OOS trades: **{len(oos['trades'])}**")
        if len(oos["trades"]): st.dataframe(oos["trades"],hide_index=True,use_container_width=True)

st.divider()
st.warning("Geen echte orders. Resultaten zijn historische simulaties met vereenvoudigde fees/slippage. Een goede backtest is geen garantie op toekomstige winst.")
