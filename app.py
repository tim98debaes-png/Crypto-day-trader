import json, os, time
from itertools import product
import numpy as np
import pandas as pd
import requests
import streamlit as st

APP_VERSION="8.0.0"
BINANCE="https://data-api.binance.vision/api/v3/klines"
COINS=["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","LINKUSDT","LTCUSDT","DOTUSDT"]
RESULTS_FILE="optimizer_results_v8.json"

st.set_page_config(page_title=f"Crypto DayTrader v{APP_VERSION}",page_icon="₿",layout="wide")

def load_results():
    if not os.path.exists(RESULTS_FILE): return {}
    try:
        with open(RESULTS_FILE,"r",encoding="utf-8") as f: return json.load(f)
    except Exception: return {}

def save_results(x):
    tmp=RESULTS_FILE+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(x,f,ensure_ascii=False,indent=2,default=str)
    os.replace(tmp,RESULTS_FILE)

@st.cache_data(ttl=300,show_spinner=False)
def fetch(symbol,interval,limit=3000):
    target=min(int(limit),10000); rows=[]; end=None
    for _ in range(30):
        if len(rows)>=target: break
        n=min(1000,target-len(rows)); params={"symbol":symbol,"interval":interval,"limit":n}
        if end is not None: params["endTime"]=end
        last=None
        for retry in range(5):
            try:
                r=requests.get(BINANCE,params=params,timeout=25,headers={"User-Agent":f"Crypto-DayTrader/{APP_VERSION}"})
                if r.status_code in (418,429): time.sleep(min(8,2**retry)); continue
                r.raise_for_status(); b=r.json(); last=None; break
            except Exception as e: last=e; time.sleep(min(5,1.5**retry))
        else: raise RuntimeError(f"Binance {symbol} {interval}: {last}")
        if not b: break
        rows=b+rows; end=b[0][0]-1
        if len(b)<n: break
        time.sleep(.1)
    if not rows: raise RuntimeError(f"Geen Binance-data voor {symbol} {interval}")
    cols=["open_time","open","high","low","close","volume","close_time","qv","trades","tb","tq","ignore"]
    d=pd.DataFrame(rows,columns=cols).drop_duplicates("open_time")
    for c in ["open","high","low","close","volume"]: d[c]=pd.to_numeric(d[c],errors="coerce")
    d["time"]=pd.to_datetime(d.open_time,unit="ms",utc=True)
    return d.sort_values("time")[["time","open","high","low","close","volume"]].dropna().tail(target).reset_index(drop=True)

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
    x["atr"]=tr.ewm(alpha=1/p["atr"],adjust=False).mean(); x["atr_pct"]=x.atr/x.close*100
    x["vol_ma"]=x.volume.rolling(20).mean()
    return x

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
    if p["atr_min"]<=r.atr_pct<=p["atr_max"]:L+=5; S+=5
    return min(L,100),min(S,100)

def mtf(symbol,limit,p):
    d5=add_ind(fetch(symbol,"5m",limit),p)
    d15=add_ind(fetch(symbol,"15m",max(500,min(3000,limit//3+100))),p)
    d1=add_ind(fetch(symbol,"1h",max(500,min(3000,limit//12+100))),p)
    def prep(d,ln,sn):
        z=d.copy(); v=[score(r,p) for _,r in z.iterrows()]
        z[ln]=[x[0] for x in v]; z[sn]=[x[1] for x in v]; z["available"]=z.time.shift(-1)
        return z[["available",ln,sn]].dropna()
    out=pd.merge_asof(d5.sort_values("time"),prep(d15,"L15","S15").sort_values("available"),left_on="time",right_on="available",direction="backward")
    out=pd.merge_asof(out.sort_values("time"),prep(d1,"L1","S1").sort_values("available"),left_on="time",right_on="available",direction="backward")
    v=[score(r,p) for _,r in out.iterrows()]
    out["L5"]=[x[0] for x in v]; out["S5"]=[x[1] for x in v]
    return out.dropna(subset=["L1","S1","L15","S15","L5","S5","atr"]).reset_index(drop=True)

def backtest(df,p,mode,capital,risk,fee,slip):
    # Fast backtest: vectorized signal generation; one compact candle loop.
    close=df["close"].to_numpy(float); high=df["high"].to_numpy(float); low=df["low"].to_numpy(float); atr=df["atr"].to_numpy(float)
    L5=df["L5"].to_numpy(float); S5=df["S5"].to_numpy(float); L15=df["L15"].to_numpy(float); S15=df["S15"].to_numpy(float); L1=df["L1"].to_numpy(float); S1=df["S1"].to_numpy(float)
    threshold=p["threshold"] if mode=="Conservatief" else max(55,p["threshold"]-10)
    L=.45*L1+.35*L15+.20*L5; S=.45*S1+.35*S15+.20*S5
    long_sig=(L>=threshold)&(L>S+8); short_sig=(S>=threshold)&(S>L+8)
    cash=float(capital); pos=0; entry=stop=tp=qty=0.0; pnls=[]; eq=np.empty(len(df),dtype=float); eq[0]=cash
    for i in range(1,len(df)):
        if pos:
            ex=None
            if pos==1:
                if low[i]<=stop: ex=stop
                elif high[i]>=tp: ex=tp
                if ex is not None:
                    ex*=1-slip/100; gross=(ex-entry)*qty
            else:
                if high[i]>=stop: ex=stop
                elif low[i]<=tp: ex=tp
                if ex is not None:
                    ex*=1+slip/100; gross=(entry-ex)*qty
            if ex is not None:
                cash += gross-(entry*qty+ex*qty)*fee/100; pnls.append(cash); pos=0
        if pos==0 and cash>0 and np.isfinite(atr[i]) and atr[i]>0:
            side=1 if long_sig[i] else -1 if short_sig[i] else 0
            if side:
                dist=max(atr[i]*p["atr_stop"],close[i]*.004); qty=cash*risk/100/dist
                if side==1:
                    entry=close[i]*(1+slip/100); stop=entry-dist; tp=entry+dist*p["rr"]
                else:
                    entry=close[i]*(1-slip/100); stop=entry+dist; tp=entry-dist*p["rr"]
                pos=side
        eq[i]=cash
    # Recover trade P&L from changes in cash at exits.
    cash_path=np.asarray(eq); dif=np.diff(cash_path); trade_pnls=dif[np.abs(dif)>1e-12]
    wins=trade_pnls[trade_pnls>0].sum() if trade_pnls.size else 0; losses=abs(trade_pnls[trade_pnls<0].sum()) if trade_pnls.size else 0
    pf=wins/losses if losses else (np.inf if wins else 0); wr=(trade_pnls>0).mean()*100 if trade_pnls.size else 0
    dd=(cash_path/np.maximum.accumulate(cash_path)-1).min()*100 if len(cash_path) else 0
    return {"return":(cash/capital-1)*100,"pf":pf,"wr":wr,"dd":dd,"trades":int(trade_pnls.size),"final":cash,"log":pd.DataFrame(),"equity":pd.Series(cash_path)}

PARAMS=[]
for fast,slow,trend in product([9,20],[21,50],[50,200]):
    if fast>=slow: continue
    for stop,rr,thr in [(1.0,1.5,65),(1.0,2.0,70),(1.25,1.5,65),(1.25,2.0,70),(1.25,2.5,75),(1.5,1.5,65),(1.5,2.0,70),(1.5,2.5,75),(1.75,1.5,65),(1.75,2.0,70),(1.75,2.5,75),(2.0,2.0,70)]:
        PARAMS.append({"fast":fast,"slow":slow,"trend":trend,"rsi":14,"atr":14,"rsi_long_low":50,"rsi_long_high":68,"rsi_short_low":32,"rsi_short_high":50,"vol_mult":1.15,"atr_min":.15,"atr_max":4,"atr_stop":stop,"rr":rr,"threshold":thr})

def optimize(symbol,days,mode,capital,risk,fee,slip):
    limit=days*24*12; candidates=[]
    keys=sorted({(p["fast"],p["slow"],p["trend"],p["rsi"]) for p in PARAMS})
    for key in keys:
        p0=dict(PARAMS[0]); p0.update({"fast":key[0],"slow":key[1],"trend":key[2],"rsi":key[3]})
        d=mtf(symbol,limit,p0)
        if len(d)<150: continue
        cut=int(len(d)*.65); train=d.iloc[:cut]
        for p in PARAMS:
            if (p["fast"],p["slow"],p["trend"],p["rsi"])!=key: continue
            r=backtest(train,p,mode,capital,risk,fee,slip)
            if r["trades"]>=20:
                q=(3 if not np.isfinite(r["pf"]) else r["pf"])+min(r["trades"]/100,1)*.15+r["return"]/100-abs(r["dd"])/100
                candidates.append((q,p,r))
    if not candidates: return {"Coin":symbol,"Status":"GEEN KANDIDAAT"}
    _,p,ins=max(candidates,key=lambda x:x[0])
    d=mtf(symbol,limit,p); cut=int(len(d)*.65); oos=backtest(d.iloc[cut:],p,mode,capital,risk,fee,slip)
    return {"Coin":symbol,"Status":"OK","IS PF":ins["pf"],"IS %":ins["return"],"IS trades":ins["trades"],"OOS PF":oos["pf"],"OOS %":oos["return"],"OOS trades":oos["trades"],"OOS WR":oos["wr"],"OOS DD":oos["dd"],"fast":p["fast"],"slow":p["slow"],"trend":p["trend"],"SL ATR":p["atr_stop"],"RR":p["rr"],"threshold":p["threshold"]}

st.title("₿ Crypto DayTrader v8.1 FAST")
st.caption("Snellere optimizer met autosave, hervatten, MTF 5m/15m/1h en OOS-validatie")

with st.sidebar:
    mode=st.radio("Strategie",["Conservatief","Agressief"])
    capital=st.number_input("Startkapitaal (€)",100.0,100000.0,1000.0,100.0)
    risk=st.slider("Risico per trade (%)",.25,2.0,1.0,.25)
    fee=st.number_input("Fee per kant (%)",0.0,.50,.10,.01)
    slip=st.number_input("Slippage per kant (%)",0.0,.50,.03,.01)
    days=st.select_slider("Onderzoeksperiode",[7,14,30],value=30)

saved=load_results()
tab1,tab2,tab3=st.tabs(["🔬 Optimizer","🏆 Robustness","📈 Live scanner"])

with tab1:
    done=sum(c in saved for c in COINS); st.progress(done/len(COINS)); st.caption(f"{done}/{len(COINS)} coins opgeslagen")
    c1,c2=st.columns(2)
    if c1.button("🧹 Wis resultaten"):
        saved={}; 
        if os.path.exists(RESULTS_FILE): os.remove(RESULTS_FILE)
        st.rerun()
    if c2.button("🚀 Start / hervat optimizer",type="primary"):
        progress=st.progress(done/len(COINS)); status=st.empty()
        for i,symbol in enumerate(COINS):
            if symbol in saved:
                status.write(f"✅ {symbol} al opgeslagen — overslaan")
                progress.progress((i+1)/len(COINS)); continue
            status.write(f"⚙️ Test {symbol} ({i+1}/{len(COINS)})...")
            try:
                row=optimize(symbol,days,mode,capital,risk,fee,slip)
                saved[symbol]={"row":row,"saved_at":pd.Timestamp.utcnow().isoformat()}
            except Exception as e:
                saved[symbol]={"row":{"Coin":symbol,"Status":"FOUT","FOUT":str(e)},"saved_at":pd.Timestamp.utcnow().isoformat()}
            save_results(saved)  # autosave after every coin
            progress.progress((i+1)/len(COINS))
        status.success("Optimizer klaar — resultaten zijn opgeslagen.")
        st.rerun()
    rows=[v["row"] for v in saved.values() if isinstance(v,dict) and "row" in v]
    if rows: st.dataframe(pd.DataFrame(rows).sort_values(["OOS PF","OOS %"],ascending=False,na_position="last"),use_container_width=True,hide_index=True)
    else: st.info("Nog geen resultaten.")

with tab2:
    rows=[v["row"] for v in saved.values() if isinstance(v,dict) and "row" in v]
    if rows:
        d=pd.DataFrame(rows)
        robust=d[(d.get("OOS PF",0).fillna(0)>=1.2)&(d.get("OOS trades",0).fillna(0)>=20)&(d.get("OOS DD",0).fillna(0)>-15)&(d.get("OOS %",0).fillna(0)>0)]
        st.success(f"{len(robust)} kandidaten voldoen aan de OOS-filters.") if len(robust) else st.warning("Geen kandidaat haalt alle OOS-filters.")
        st.dataframe(robust,use_container_width=True,hide_index=True)
    else: st.info("Voer eerst de optimizer uit.")

with tab3:
    selected=st.multiselect("Coins",COINS,default=COINS[:5])
    if st.button("🔎 Scan nu"):
        rows=[]
        for s in selected:
            try:
                p=PARAMS[0]; d=mtf(s,1000,p); r=d.iloc[-1]; l5,s5=score(r,p)
                L=.45*r.L1+.35*r.L15+.20*l5; S=.45*r.S1+.35*r.S15+.20*s5
                sig="LONG" if L>=70 and L>S+8 else "SHORT" if S>=70 and S>L+8 else "WAIT"
                rows.append({"Coin":s,"Signal":sig,"Score":max(L,S),"1H":max(r.L1,r.S1),"15M":max(r.L15,r.S15),"5M":max(l5,s5),"Price":r.close})
            except Exception as e: rows.append({"Coin":s,"Signal":"ERROR","Score":0,"Error":str(e)})
        st.dataframe(pd.DataFrame(rows).sort_values("Score",ascending=False),use_container_width=True,hide_index=True)

st.divider()
st.warning("Onderzoekstool — geen financieel advies en geen live orders.")
