"""Research-stage bidirectional entry/exit logic with pullback confirmation."""
from __future__ import annotations


def ema(values: list[float], period: int) -> float | None:
    if not values: return None
    alpha=2.0/(period+1.0); result=values[0]
    for value in values[1:]: result=alpha*value+(1-alpha)*result
    return result


def entry_signal_details(prices:list[float],direction:str="LONG"):
    if len(prices)<12:return False,"insufficient_history",0,{}
    direction=direction.upper()
    if direction not in {"LONG","SHORT"}:return False,"invalid_direction",0,{}
    price=prices[-1];fast=ema(prices[-8:],5);slow=ema(prices[-12:],10)
    if fast is None or slow is None:return False,"insufficient_history",0,{}
    short=price/prices[-4]-1;medium=price/prices[-10]-1;recent=[prices[i]/prices[i-1]-1 for i in range(len(prices)-3,len(prices))];positive=sum(x>0 for x in recent);negative=sum(x<0 for x in recent);window=prices[-7:-3]
    touched=(min(window)<=fast*1.0015) if direction=="LONG" else (max(window)>=fast*0.9985)
    confirmations={"trend":fast>=slow if direction=="LONG" else fast<=slow,"price_near_fast":price>=fast*.999 if direction=="LONG" else price<=fast*1.001,"medium_momentum":medium>=.0005 if direction=="LONG" else medium<=-.0005,"short_momentum":short>=.0005 if direction=="LONG" else short<=-.0005,"positive_microstructure":positive>=2 if direction=="LONG" else negative>=2}
    score=sum(confirmations.values())
    if direction=="LONG":
        if fast<slow*.9985 or price<slow*.997:return False,"trend_not_confirmed",score,confirmations
        if price>fast*1.0065:return False,"overextended",score,confirmations
        if negative==3:return False,"short_term_reversal",score,confirmations
    else:
        if fast>slow*1.0015 or price>slow*1.003:return False,"trend_not_confirmed",score,confirmations
        if price<fast*.9935:return False,"overextended",score,confirmations
        if positive==3:return False,"short_term_reversal",score,confirmations
    if not touched:return False,"pullback_not_confirmed",score,confirmations
    if score<4:return False,"momentum_not_confirmed",score,confirmations
    return True,"confirmed",score,confirmations


def entry_signal(prices:list[float],direction:str="LONG"):
    ready,reason,_,_=entry_signal_details(prices,direction);return ready,reason


def exit_signal(prices:list[float],direction:str="LONG"):
    if len(prices)<12:return False
    direction=direction.upper();fast=ema(prices[-8:],5);slow=ema(prices[-12:],10)
    if fast is None or slow is None:return False
    recent=[prices[i]/prices[i-1]-1 for i in range(len(prices)-3,len(prices)-0)];negative=sum(x<0 for x in recent);positive=sum(x>0 for x in recent);short=prices[-1]/prices[-4]-1
    if direction=="LONG":return prices[-1]<fast*.9985 and fast<slow and (negative==3 or (negative>=2 and short<-.0008))
    return prices[-1]>fast*1.0015 and fast>slow and (positive==3 or (positive>=2 and short>.0008))
