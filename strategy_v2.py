"""Independent Strategy V2: multi-timeframe trend pullback continuation."""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from typing import Mapping, Sequence

@dataclass(frozen=True)
class StrategyV2Signal:
    direction: str
    score: int
    reason: str
    entry_price: float
    stop_distance: float
    features: Mapping[str, float | bool]

def _f(value: object) -> float | None:
    try:x=float(value)
    except(TypeError,ValueError):return None
    return x if isfinite(x) else None

def _field(candle:Mapping[str,object],name:str)->float|None:return _f(candle.get(name))
def _closes(candles:Sequence[Mapping[str,object]])->list[float]:
    out=[]
    for c in candles:
        v=_field(c,"close")
        if v is None or v<=0:return []
        out.append(v)
    return out

def _ema(values:Sequence[float],period:int)->float|None:
    if len(values)<period:return None
    a=2/(period+1);r=values[0]
    for v in values[1:]:r=a*v+(1-a)*r
    return r

def _atr(candles:Sequence[Mapping[str,object]],period:int=14)->float|None:
    if len(candles)<period+1:return None
    p=_field(candles[-period-1],"close")
    if p is None:return None
    trs=[]
    for c in candles[-period:]:
        h,l,cl=_field(c,"high"),_field(c,"low"),_field(c,"close")
        if h is None or l is None or cl is None or h<l:return None
        trs.append(max(h-l,abs(h-p),abs(l-p)));p=cl
    return sum(trs)/len(trs)

def _slope(values:Sequence[float],lookback:int)->float|None:
    if len(values)<lookback+1:return None
    return values[-1]/values[-1-lookback]-1

def _relative_volume(candles:Sequence[Mapping[str,object]],lookback:int=20)->float|None:
    if len(candles)<lookback+1:return None
    cur=_field(candles[-1],"volume");hist=[_field(c,"volume") for c in candles[-lookback-1:-1]
    if cur is None or cur<0 or any(v is None or v<0 for v in hist):return None
    avg=sum(v for v in hist if v is not None)/len(hist)
    return cur/avg if avg>0 else None

def _structure(candles:Sequence[Mapping[str,object]],direction:str)->tuple[bool,bool]:
    if len(candles)<5:return False,False
    hs=[_field(c,"high") for c in candles[-5:]];ls=[_field(c,"low") for c in candles[-5:]]
    if any(v is None for v in hs+ls):return False,False
    h=[float(v) for v in hs if v is not None];l=[float(v) for v in ls if v is not None]
    if direction=="LONG":return h[-1]>h[-2] and l[-1]>l[-2],h[-1]>h[0] and l[-1]>l[0]
    return h[-1]<h[-2] and l[-1]<l[-2],h[-1]<h[0] and l[-1]<l[0]

def _pullback_trigger(candles:Sequence[Mapping[str,object]],direction:str,atr:float,ema_fast:float)->tuple[bool,float]:
    if len(candles)<5 or atr<=0:return False,0
    cur,prev=candles[-1],candles[-2];close,high,low,op=_field(cur,"close"),_field(cur,"high"),_field(cur,"low"),_field(cur,"open");pc,pl,ph=_field(prev,"close"),_field(prev,"low"),_field(prev,"high");ls=[_field(c,"low") for c in candles[-5:-1]];hs=[_field(c,"high") for c in candles[-5:-1]]
    if None in(close,high,low,op,pc,pl,ph) or any(v is None for v in ls+hs):return False,0
    body=abs(close-op)
    if direction=="LONG":
        pb=min(v for v in ls if v is not None);reclaim=close>ema_fast and pc<=ema_fast;impulse=close>ph and body/atr>=.30 and close>op;depth=max(0,(ema_fast-pb)/atr)
    else:
        pb=max(v for v in hs if v is not None);reclaim=close<ema_fast and pc>=ema_fast;impulse=close<pl and body/atr>=.30 and close<op;depth=max(0,(pb-ema_fast)/atr)
    return reclaim and impulse and .15<=depth<=1.5,depth

def generate_signal(candles_5m:Sequence[Mapping[str,object]],candles_15m:Sequence[Mapping[str,object]],candles_1h:Sequence[Mapping[str,object]],btc_1h:Sequence[Mapping[str,object]]|None=None)->StrategyV2Signal|None:
    if min(len(candles_5m),len(candles_15m),len(candles_1h))<50:return None
    c5,c15,c1=_closes(candles_5m),_closes(candles_15m),_closes(candles_1h)
    if not c5 or not c15 or not c1:return None
    e1f,e1s,e15f,e15s,e5f,a5,rv=_ema(c1,20),_ema(c1,50),_ema(c15,20),_ema(c15,50),_ema(c5,20),_atr(candles_5m),_relative_volume(candles_5m)
    if None in(e1f,e1s,e15f,e15s,e5f,a5,rv):return None
    s15,s1=_slope(c15,4),_slope(c1,4)
    if s15 is None or s1 is None:return None
    bd=None
    if btc_1h is not None:
        b=_closes(btc_1h);bf,bs=_ema(b,20),_ema(b,50)
        if bf is None or bs is None:return None
        bd="LONG" if bf>=bs else "SHORT"
    candidates=[]
    for direction in("LONG","SHORT"):
        trend=(e1f>e1s and e15f>e15s and s15>0 and s1>0) if direction=="LONG" else(e1f<e1s and e15f<e15s and s15<0 and s1<0)
        structure,continuation=_structure(candles_15m,direction);trigger,depth=_pullback_trigger(candles_5m,direction,a5,e5f);participation=rv>=1;btc_ok=bd is None or bd==direction;score=sum((trend,structure,continuation,trigger,participation,btc_ok))
        if score<6:continue
        price=c5[-1];candidates.append(StrategyV2Signal(direction,score,"v2_trend_pullback_continuation",price,max(a5*1.5,price*.003),{"trend":trend,"structure":structure,"continuation":continuation,"trigger":trigger,"participation":participation,"btc_ok":btc_ok,"pullback_depth_atr":depth,"relative_volume":rv,"slope_15m":s15,"slope_1h":s1}))
    return max(candidates,key=lambda x:x.score) if candidates else None
