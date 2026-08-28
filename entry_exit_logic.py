"""Research-stage bidirectional entry/exit logic with pullback confirmation."""
from __future__ import annotations


def ema(values: list[float], period: int) -> float | None:
    if not values: return None
    alpha = 2.0 / (period + 1.0); result = values[0]
    for value in values[1:]: result = alpha * value + (1.0 - alpha) * result
    return result


def entry_signal_details(prices: list[float], direction: str = "LONG") -> tuple[bool, str, int, dict[str, bool]]:
    """Return a directional entry decision and five-factor confirmation breakdown.

    The timing gate requires a trend-aligned pullback followed by renewed momentum,
    rather than entering merely because the trend is already extended.
    """
    if len(prices) < 12: return False, "insufficient_history", 0, {}
    direction = direction.upper()
    if direction not in {"LONG", "SHORT"}: return False, "invalid_direction", 0, {}
    price=prices[-1]; fast=ema(prices[-8:],5); slow=ema(prices[-12:],10)
    if fast is None or slow is None: return False, "insufficient_history", 0, {}
    short_return=price/prices[-4]-1.0; medium_return=price/prices[-10]-1.0
    recent=[prices[i]/prices[i-1]-1.0 for i in range(len(prices)-3,len(prices))]
    positive=sum(1 for move in recent if move>0); negative=sum(1 for move in recent if move<0)
    pullback_window=prices[-7:-3]
    pullback_fast=ema(pullback_window,5) if len(pullback_window)>=5 else None
    pullback_touched=(min(pullback_window) <= fast*1.0015) if direction=="LONG" and pullback_window else (max(pullback_window) >= fast*0.9985 if pullback_window else False)
    renewed=(short_return >= 0.0005 and positive >= 2) if direction=="LONG" else (short_return <= -0.0005 and negative >= 2)
    confirmations={
        "trend": fast>=slow if direction=="LONG" else fast<=slow,
        "price_near_fast": price>=fast*0.999 if direction=="LONG" else price<=fast*1.001,
        "medium_momentum": medium_return>=0.0005 if direction=="LONG" else medium_return<=-0.0005,
        "short_momentum": renewed,
        "positive_microstructure": positive>=2 if direction=="LONG" else negative>=2,
    }
    score=sum(confirmations.values())
    if direction=="LONG":
        if fast < slow*0.9985 or price < slow*0.9970: return False,"trend_not_confirmed",score,confirmations
        if price > fast*1.0065: return False,"overextended",score,confirmations
        if negative==3: return False,"short_term_reversal",score,confirmations
        if not pullback_touched: return False,"pullback_not_confirmed",score,confirmations
    else:
        if fast > slow*1.0015 or price > slow*1.0030: return False,"trend_not_confirmed",score,confirmations
        if price < fast*0.9935: return False,"overextended",score,confirmations
        if positive==3: return False,"short_term_reversal",score,confirmations
        if not pullback_touched: return False,"pullback_not_confirmed",score,confirmations
    if score < 4: return False,"momentum_not_confirmed",score,confirmations
    return True,"confirmed",score,confirmations


def entry_signal(prices: list[float], direction: str = "LONG") -> tuple[bool,str]:
    ready,reason,_score,_confirmations=entry_signal_details(prices,direction)
    return ready,reason


def exit_signal(prices: list[float], direction: str = "LONG") -> bool:
    if len(prices)<12: return False
    direction=direction.upper(); fast=ema(prices[-8:],5); slow=ema(prices[-12:],10)
    if fast is None or slow is None: return False
    recent=[prices[i]/prices[i-1]-1.0 for i in range(len(prices)-3,len(prices))]
    negative=sum(1 for x in recent if x<0); positive=sum(1 for x in recent if x>0); short_return=prices[-1]/prices[-4]-1.0
    if direction=="LONG": return prices[-1]<fast*0.9985 and fast<slow and (negative==3 or (negative>=2 and short_return<-0.0008))
    return prices[-1]>fast*1.0015 and fast>slow and (positive==3 or (positive>=2 and short_return>0.0008))
