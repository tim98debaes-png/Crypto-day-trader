"""Legacy strategy adapter isolated from the Streamlit research UI."""
from __future__ import annotations
import numpy as np
from app import indicators, make_signals, STRATEGIES

def prepare(data): return indicators(data)
def signals(data,params,mode="Conservatief"):
    x=prepare(data) if "ema20_1h" not in data.columns else data
    long_score,short_score=make_signals(x,params); threshold=params["threshold"]-(5 if mode=="Agressief" else 0)
    long=(long_score>=threshold)&(long_score>short_score+params["min_edge"]); short=(short_score>=threshold)&(short_score>long_score+params["min_edge"])
    return long,short
def candidate_grid(): return [dict(p) for p in STRATEGIES]
def summary_grid():
    families={}
    for p in STRATEGIES: families[p["family"]]=families.get(p["family"],0)+1
    return {"total_candidates":len(STRATEGIES),"families":families}
