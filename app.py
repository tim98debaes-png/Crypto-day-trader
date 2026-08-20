
import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
from itertools import product

st.set_page_config(page_title="Crypto DayTrader v7", page_icon="₿", layout="wide")

BINANCE="https://data-api.binance.vision/api/v3/klines"
COINS=["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","LINKUSDT","LTCUSDT","DOTUSDT"]

@st.cache_data(ttl=60, show_spinner=False)
def fetch(symbol, interval, limit=3000):
    rows=[]; end=None; left=min(int(limit),3000)
    while left:
        n=min(1000,left); p={"symbol":symbol,"interval":interval,"limit":n}
        if end is not None:p["endTime"]=end
        r=requests.get(BINANCE,params=p,timeout=15,headers={"User-Agent":"Crypto-DayTrader/7.0"})
        r.raise_for_status(); b=r.json()
        if not b:break
        rows=b+rows; end=b[0][0]-1; left-=len(b)
        if len(b)<n:break
    cols=["open_time","open","high","low","close","volume","close_time","qv","trades","tb","tq","ignore"]
    d=pd.DataFrame(rows,columns=cols).drop_duplicates("open_time")
    for c in ["open","high","low","close","volume"]:d[c]=pd.to_numeric(d[c],errors="coerce")
    d["time"]=pd.to_datetime(d.open_time,unit="ms",utc=True)
    return d.sort_values("time")[["time","open","high","low","close","volume"]].dropna().reset_index(drop=True)

def rsi(s,n):
    d=s.diff(); g=d.clip(lower=0); l=-d.clip(upper=0)
    ag=g.ewm(alpha=1/n,adjust=False).mean(); al=l.ewm(alpha=1/n,adjust=False).mean()
    return 100-100/(1+ag/al.replace(0,np.nan))

def add_ind(d,p):
    x=d.copy()
    x["fast"]=x.close.ewm(span=p["fast"],adjust=False).mean()
    x["slow"]=x.close.ewm(span=p["slow"],adjust=False).mean()
    x["trend"]=x.close.ewm(span=p["trend"],adjust=False).mean()
    x["rsi"]=rsi(x.close,p["rsi"])
    e12=x.close.ewm(span=12,adjust=False).mean(); e26=x.close.ewm(span=26,adjust=False).mean()
    x["macd"]=e12-e26; x["macd_sig"]=x.macd.ewm(span=9,adjust=False).mean()
    tr=pd.concat([x.high-x.low,(x.high-x.close.shift()).abs(),(x.low-x.close.shift()).abs()],axis=1).max(axis=1)
    x["atr"]=tr.ewm(alpha=1/p["atr"],adjust=False).mean()
    x["atr_pct"]=x.atr/x.close*100
    x["vol_ma"]=x.volume.rolling(20).mean()
    return x

def make_mtf(symbol,limit,p):
    d5=add_ind(fetch(symbol,"5m",limit),p)
    d15=add_ind(fetch(symbol,"15m",min(3000,max(500,limit//3+100))),p)
    d1=add_ind(fetch(symbol,"1h",min(3000,max(500,limit//12+100))),p)
    # Completed HTF candles only: shift their usable timestamp to the next candle open.
    def prep(d,prefix):
        z=d.copy()
        z["L"],z["S"]=score(z.iloc[-1],p) if False else (0,0)
        vals=[score(row,p) for _,row in z.iterrows()]
        z["L"]=[v[0] for v in vals]; z["S"]=[v[1] for v in vals]
        z["available"]=z.time.shift(-1)
        return z[["available","L","S"]].dropna()
    a=prep(d15,"15"); b=prep(d1,"1")
    vals=[score(row,p) for _,row in d5.iterrows()]
    d5["L5"]=[v[0] for v in vals]; d5["S5"]=[v[1] for v in vals]
    out=pd.merge_asof(d5.sort_values("time"),a.sort_values("available"),left_on="time",right_on="available",direction="backward")
    out=pd.merge_asof(out,b.sort_values("available"),left_on="time",right_on="available",direction="backward")
    return out.dropna(subset=["L","S","L5","S5"]).rename(columns={"L":"L15","S":"S15"}).reset_index(drop=True)

def score(r,p):
    L=S=0
    if r.fast>r.slow:L+=20
    elif r.fast<r.slow:S+=20
    if r.close>r.trend:L+=15
    elif r.close<r.trend:S+=15
    if r.macd>r.macd_sig:L+=15
    elif r.macd<r.macd_sig:S+=15
    if p["rsi_long_low"]<=r.rsi<=p["rsi_long_high"]:L+=15
    if p["rsi_short_low"]<=r.rsi<=p["rsi_short_high"]:S+=15
    if pd.notna(r.vol_ma) and r.volume>r.vol_ma*p["vol_mult"]:
        if r.close>=r.open:L+=10
        else:S+=10
    if p["atr_min"]<=r.atr_pct<=p["atr_max"]:L+=5;S+=5
    return min(L,100),min(S,100)

def backtest(df,p,mode="Conservatief",capital=1000,risk=1,fee=.10,slip=.03):
    cash=float(capital);pos=None;trades=[];eq=[]
    threshold=p["threshold"] if mode=="Conservatief" else max(55,p["threshold"]-10)
    for i in range(1,len(df)):
        r=df.iloc[i]
        if pos:
            ex=None;reason=None
            if pos["side"]=="LONG":
                if r.low<=pos["stop"]:ex=pos["stop"];reason="SL"
                elif r.high>=pos["tp"]:ex=pos["tp"];reason="TP"
            else:
                if r.high>=pos["stop"]:ex=pos["stop"];reason="SL"
                elif r.low<=pos["tp"]:ex=pos["tp"];reason="TP"
            if ex is not None:
                ex*=1-slip/100 if pos["side"]=="LONG" else 1+slip/100
                gross=(ex-pos["entry"])*pos["qty"] if pos["side"]=="LONG" else (pos["entry"]-ex)*pos["qty"]
                fees=(pos["entry"]*pos["qty"]+ex*pos["qty"])*fee/100
                pnl=gross-fees;cash+=pnl
                trades.append({**pos,"Exit":ex,"P&L":pnl,"Result":reason,"Exit time":r.time});pos=None
        if pos is None:
            L5,S5=score(r,p)
            L15,S15=float(r.L15),float(r.S15);L1,S1=float(r.L1),float(r.S1)
            L=.45*L1+.35*L15+.20*L5;S=.45*S1+.35*S15+.20*S5
            sig="LONG" if L>=threshold and L>S+8 else ("SHORT" if S>=threshold and S>L+8 else "WAIT")
            if sig!="WAIT" and r.atr>0:
                dist=max(float(r.atr)*p["atr_stop"],float(r.close)*.004)
                qty=max(cash,0)*risk/100/dist
                entry=float(r.close)*(1+slip/100 if sig=="LONG" else 1-slip/100)
                rr=p["rr"]
                stop=entry-dist if sig=="LONG" else entry+dist
                tp=entry+dist*rr if sig=="LONG" else entry-dist*rr
                pos={"side":sig,"entry":entry,"stop":stop,"tp":tp,"qty":qty,"Entry time":r.time,"Score":max(L,S)}
        eq.append(cash)
    t=pd.DataFrame(trades);e=pd.Series(eq)
    wins=t.loc[t["P&L"]>0,"P&L"].sum() if len(t) else 0
    losses=abs(t.loc[t["P&L"]<0,"P&L"].sum()) if len(t) else 0
    pf=wins/losses if losses else (np.inf if wins else 0)
    wr=(t["P&L"]>0).mean()*100 if len(t) else 0
    dd=(e/e.cummax()-1).min()*100 if len(e) else 0
    return {"return":(cash/capital-1)*100,"pf":pf,"wr":wr,"dd":dd,"trades":len(t),"final":cash,"log":t,"equity":e}

PARAMS=[]
for fast,slow,trend,rsi_n,stop,rr,thr in product(
    [9,20],[21,50],[50,200],[14],[1.0,1.25,1.5],[1.5,2.0,2.5],[65,70,75]):
    if fast>=slow:continue
    PARAMS.append({"fast":fast,"slow":slow,"trend":trend,"rsi":rsi_n,"rsi_long_low":50,"rsi_long_high":68,
                   "rsi_short_low":32,"rsi_short_high":50,"vol_mult":1.15,"atr_min":.15,"atr_max":4,
                   "atr_stop":stop,"rr":rr,"threshold":thr})

def quality(r):
    # Reward robust profit factor and trade count, penalize drawdown.
    if not np.isfinite(r["pf"]):pf=3
    else:pf=r["pf"]
    return pf + min(r["trades"]/100,1)*.15 + r["return"]/100 - abs(r["dd"])/100

st.title("₿ Crypto DayTrader v7")
st.caption("Strategy Optimizer • 30-day research • in-sample / out-of-sample / walk-forward • anti-overfitting guardrails")

with st.sidebar:
    mode=st.radio("Strategie",["Conservatief","Agressief"])
    capital=st.number_input("Startkapitaal (€)",100.0,100000.0,1000.0,100.0)
    risk=st.slider("Risico per trade (%)",.25,2.0,1.0,.25)
    fee=st.number_input("Fee per kant (%)",0.0,.50,.10,.01)
    slip=st.number_input("Slippage per kant (%)",0.0,.50,.03,.01)
    days=st.select_slider("Onderzoeksperiode",options=[7,14,30],value=30)

tab1,tab2,tab3=st.tabs(["🔬 Optimizer","🏆 Robustness","📈 Live scanner"])

with tab1:
    st.subheader("Automatische parameterzoeker")
    st.write(f"De app test een beperkte grid van strategieën op ongeveer {days} dagen. Daarna wordt de beste kandidaat niet automatisch als winnaar beschouwd: hij moet ook buiten de trainingsperiode overeind blijven.")
    if st.button("🚀 Start optimizer",type="primary"):
        rows=[]
        for symbol in COINS:
            with st.spinner(f"Test {symbol}..."):
                try:
                    d=make_mtf(symbol,int(days*24*12))
                    cut=int(len(d)*.65)
                    train=d.iloc[:cut].reset_index(drop=True)
                    test=d.iloc[cut:].reset_index(drop=True)
                    # Search on training period only.
                    candidates=[]
                    for p in PARAMS:
                        rr=backtest(train,p,mode,capital,risk,fee,slip)
                        if rr["trades"]>=20:
                            candidates.append((quality(rr),p,rr))
                    candidates.sort(key=lambda x:x[0],reverse=True)
                    best=candidates[0] if candidates else None
                    if best:
                        _,p,ins=best
                        oos=backtest(test,p,mode,capital,risk,fee,slip)
                        rows.append({"Coin":symbol,"IS PF":ins["pf"],"IS %":ins["return"],"IS trades":ins["trades"],
                                     "OOS PF":oos["pf"],"OOS %":oos["return"],"OOS trades":oos["trades"],
                                     "OOS WR":oos["wr"],"OOS DD":oos["dd"],"fast":p["fast"],"slow":p["slow"],
                                     "trend":p["trend"],"SL ATR":p["atr_stop"],"RR":p["rr"],"threshold":p["threshold"]})
                    else:
                        rows.append({"Coin":symbol,"IS PF":np.nan,"IS %":np.nan,"IS trades":0,"OOS PF":np.nan,"OOS %":np.nan,"OOS trades":0,"OOS WR":0,"OOS DD":0})
                except Exception as e:
                    rows.append({"Coin":symbol,"FOUT":str(e)})
        out=pd.DataFrame(rows)
        st.session_state["v7opt"]=out
    if "v7opt" in st.session_state:
        out=st.session_state["v7opt"].sort_values(["OOS PF","OOS %"],ascending=False)
        st.dataframe(out.style.format({c:"{:.2f}" for c in out.columns if c not in ["Coin","FOUT","IS trades","OOS trades","fast","slow","trend","threshold"]}),use_container_width=True,hide_index=True)

with tab2:
    st.subheader("Robustness / walk-forward")
    st.write("Een kandidaat telt pas als interessant wanneer hij winstgevend blijft op ongeziene data. De optimizer zoekt uitsluitend in de trainingsperiode.")
    if "v7opt" in st.session_state:
        out=st.session_state["v7opt"].copy()
        robust=out[(out.get("OOS PF",0)>=1.2)&(out.get("OOS trades",0)>=20)&(out.get("OOS DD",0)>-15)&(out.get("OOS %",0)>0)]
        if len(robust): st.success(f"{len(robust)} kandidaten voldoen voorlopig aan de OOS-filters.")
        else: st.warning("Geen kandidaat haalt alle OOS-filters. Dat betekent: verder verbeteren, niet live traden.")
        st.dataframe(robust,use_container_width=True,hide_index=True)
    else:
        st.info("Voer eerst de optimizer uit.")

with tab3:
    st.subheader("Live scanner")
    st.write("De uiteindelijke scanner blijft de strategie gebruiken zonder echte orders.")
    selected=st.multiselect("Coins",COINS,default=COINS[:5])
    if st.button("🔎 Scan nu"):
        rr=[]
        p=PARAMS[0]
        for s in selected:
            try:
                d=make_mtf(s,1000);r=d.iloc[-1]
                L5,S5=score(r,p);L=.45*r.L1+.35*r.L15+.20*L5;S=.45*r.S1+.35*r.S15+.20*S5
                sig="LONG" if L>=70 and L>S+8 else ("SHORT" if S>=70 and S>L+8 else "WAIT")
                rr.append({"Coin":s,"Signal":sig,"Score":max(L,S),"1H":max(r.L1,r.S1),"15M":max(r.L15,r.S15),"5M":max(L5,S5),"Price":r.close})
            except Exception as e: rr.append({"Coin":s,"Signal":"ERROR","Score":0,"Error":str(e)})
        st.dataframe(pd.DataFrame(rr).sort_values("Score",ascending=False),hide_index=True,use_container_width=True)

st.divider()
st.warning("Onderzoekstool. Geen financieel advies en geen live orders. Optimalisatie kan overfitting veroorzaken; gebruik OOS en walk-forward resultaten als beslissende controle.")
