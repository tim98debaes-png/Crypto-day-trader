"""Bounded multi-asset public-feed paper session with directional pullback entries."""
from __future__ import annotations
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable
from entry_exit_logic import entry_signal_details, exit_signal
from multi_asset_scanner import AssetSnapshot, DEFAULT_LIQUID_UNIVERSE, RESEARCH_MIN_QUOTE_VOLUME, rank_assets
from paper_execution import PaperExecutionLoop
from strategy_risk_controls import RISK_CONFIG, exceeds_correlation_limit, sector_position_count

TIER_A_MIN_SCORE=4; TIER_B_MIN_SCORE=3; TIER_B_RISK_PCT=0.25
@dataclass(frozen=True)
class MultiAssetPaperResult:
    duration_minutes:int; universe_size:int; scan_cycles:int; successful_snapshots:int; feed_errors:int; candidate_symbols:tuple[str,...]; summary:dict; diagnostics:dict

def _ema(values:list[float],period:int)->float|None:
    if not values:return None
    alpha=2.0/(period+1.0); result=values[0]
    for value in values[1:]:result=alpha*value+(1-alpha)*result
    return result

def _empty_trade_stats()->dict:return {"trades":0,"wins":0,"losses":0,"gross_profit":0.0,"gross_loss":0.0,"net_pnl":0.0}
def _finalize_trade_stats(stats:dict)->dict:
    r=dict(stats);r["win_rate_pct"]=r["wins"]/r["trades"]*100 if r["trades"] else 0.0;r["profit_factor"]=r["gross_profit"]/r["gross_loss"] if r["gross_loss"] else (float("inf") if r["gross_profit"] else 0.0);return r

def _audit_diagnostics(audit_log:list[dict])->dict:
    opens={}; score_groups={f"{x}/5":_empty_trade_stats() for x in (3,4,5)}; tier_groups={"A":_empty_trade_stats(),"B":_empty_trade_stats()}; direction_groups={"LONG":_empty_trade_stats(),"SHORT":_empty_trade_stats()}; coin_groups={}; exit_groups={}; execution=[]
    for event in audit_log:
        symbol=str(event.get("symbol",""));kind=str(event.get("event","")).upper()
        if kind=="OPEN":opens[symbol]=event;continue
        if kind!="CLOSE":continue
        opened=opens.pop(symbol,{});pnl=float(event.get("pnl",0));score=event.get("strategy_score",opened.get("strategy_score"));tier=event.get("strategy_tier",opened.get("strategy_tier"));direction=str(event.get("direction",opened.get("direction","UNKNOWN"))).upper();reason=str(event.get("reason","UNKNOWN"));groups=[]
        if score is not None and int(score) in (3,4,5):groups.append(score_groups[f"{int(score)}/5"])
        if tier in tier_groups:groups.append(tier_groups[tier])
        direction_groups.setdefault(direction,_empty_trade_stats());groups.append(direction_groups[direction]);coin_groups.setdefault(symbol,_empty_trade_stats());groups.append(coin_groups[symbol]);exit_groups.setdefault(reason,_empty_trade_stats());groups.append(exit_groups[reason])
        for s in groups:s["trades"]+=1;s["net_pnl"]+=pnl;s["wins"]+=pnl>=0;s["losses"]+=pnl<0;s["gross_profit"]+=max(pnl,0);s["gross_loss"]+=max(-pnl,0)
        execution.append({k:event.get(k) for k in ("symbol","direction","price","pnl","reason","intended_risk_amount","intended_stop_price","actual_loss_amount","risk_to_actual_ratio","stop_gap_pct","timestamp")})
    return {"score_groups":{k:_finalize_trade_stats(v) for k,v in score_groups.items()},"tier_groups":{k:_finalize_trade_stats(v) for k,v in tier_groups.items()},"direction_groups":{k:_finalize_trade_stats(v) for k,v in direction_groups.items()},"coin_groups":{k:_finalize_trade_stats(v) for k,v in sorted(coin_groups.items())},"exit_groups":{k:_finalize_trade_stats(v) for k,v in sorted(exit_groups.items())},"execution_audit":execution}

def run_multi_asset_paper_session(*,feed,loop:PaperExecutionLoop,duration_seconds:int=3600,interval_seconds:int=30,universe:tuple[str,...]=DEFAULT_LIQUID_UNIVERSE,sleep:Callable[[float],None]=time.sleep,clock:Callable[[],float]=time.monotonic)->MultiAssetPaperResult:
    if duration_seconds<=0 or interval_seconds<=0:raise ValueError("duration_seconds and interval_seconds must be positive")
    symbols=tuple(dict.fromkeys(str(s).upper() for s in universe if s));started=clock();cycles=successful=errors=0;selected=[];history={s:deque(maxlen=max(20,RISK_CONFIG.correlation_window+12)) for s in symbols};failure={s:0 for s in symbols};quarantined=set()
    diagnostics={"assets_attempted":0,"liquidity_rejections":0,"ranked_candidates":0,"entry_momentum_rejections":0,"entry_volatility_rejections":0,"entry_trend_rejections":0,"entry_overextension_rejections":0,"entry_reversal_rejections":0,"pullback_rejections":0,"market_regime_rejections":0,"correlation_rejections":0,"sector_rejections":0,"position_cap_rejections":0,"entry_ready":0,"opened_trades":0,"closed_trades":0,"signal_exits":0,"peak_open_positions":0,"research_gate_rejections":0,"quarantined_symbols":[],"tier_a_ready":0,"tier_b_ready":0,"tier_a_opened":0,"tier_b_opened":0,"score_counts":{"3/5":0,"4/5":0,"5/5":0},"direction_counts":{"LONG":0,"SHORT":0}}
    while clock()-started<duration_seconds:
        cycles+=1;snapshots=[];diagnostics["assets_attempted"]+=len(symbols)-len(quarantined)
        for symbol in tuple(loop.account.positions.keys()):
            try:
                snap=feed.snapshot(symbol);prices=history[symbol];prices.append(float(snap.price));atr=max(float(snap.price)*max(float(getattr(snap,"volatility_pct",0)),.05)/100*.5,float(snap.price)*.001);direction=loop.account.positions[symbol].direction;result=loop.on_market({"symbol":snap.symbol,"price":snap.price,"direction":direction,"stop_distance":max(snap.price*.006,atr*1.8,1e-8),"atr_distance":atr,"timestamp":snap.timestamp},exit_signal=exit_signal(list(prices),direction));successful+=1
                if result.get("action")=="CLOSE" and result.get("reason")=="SIGNAL":diagnostics["signal_exits"]+=1
            except Exception:errors+=1
        for symbol in symbols:
            if symbol in quarantined:continue
            try:
                snap=feed.snapshot(symbol);price=float(snap.price);failure[symbol]=0;prices=history[symbol];prices.append(price);change=((price/prices[0])-1)*100 if len(prices)>=3 else 0;moves=[abs((prices[i]/prices[i-1]-1)*100) for i in range(1,len(prices))];snapshots.append(AssetSnapshot(symbol,price,float(getattr(snap,"quote_volume",0)),change,max(moves,default=0)));successful+=1
            except Exception:
                errors+=1;failure[symbol]+=1
                if failure[symbol]>=3:quarantined.add(symbol)
        ranked=rank_assets(snapshots,min_quote_volume=RESEARCH_MIN_QUOTE_VOLUME,max_candidates=10);diagnostics["ranked_candidates"]+=len(ranked)
        btc=list(history.get("BTCUSDT",()));btcema=_ema(btc,20) if len(btc)>=5 else None
        for candidate in ranked:
            live=next(s for s in snapshots if s.symbol==candidate.symbol);prices=list(history[candidate.symbol]);
            # Evaluate both directions; only the direction whose own trend/pullback setup is confirmed can open.
            options=[]
            for direction in ("LONG","SHORT"):
                ready,reason,score,conf=entry_signal_details(prices,direction)
                tier="A" if ready and score>=4 else ("B" if reason=="momentum_not_confirmed" and score==3 and conf.get("trend") and conf.get("medium_momentum") and conf.get("positive_microstructure") else None)
                if tier:options.append((direction,tier,score,reason))
                elif reason=="pullback_not_confirmed":diagnostics["pullback_rejections"]+=1
                elif reason=="short_term_reversal":diagnostics["entry_reversal_rejections"]+=1
                elif reason=="trend_not_confirmed":diagnostics["entry_trend_rejections"]+=1
                elif reason=="overextended":diagnostics["entry_overextension_rejections"]+=1
                else:diagnostics["entry_momentum_rejections"]+=1
            if not options:continue
            direction,tier,score,_=max(options,key=lambda x:x[2]);diagnostics["score_counts"][f"{score}/5"]+=1;diagnostics[f"tier_{tier.lower()}_ready"]+=1;diagnostics["direction_counts"][direction]+=1
            if not (RISK_CONFIG.volatility_floor_pct<=live.volatility_pct<=RISK_CONFIG.volatility_ceiling_pct):diagnostics["entry_volatility_rejections"]+=1;continue
            if live.symbol!="BTCUSDT" and btcema is not None:
                btc_ok=btc[-1]>=btcema if direction=="LONG" else btc[-1]<=btcema
                if not btc_ok:diagnostics["market_regime_rejections"]+=1;continue
            if live.symbol in loop.account.positions:continue
            if len(loop.account.positions)>=RISK_CONFIG.max_open_positions:diagnostics["position_cap_rejections"]+=1;continue
            if sector_position_count(live.symbol,tuple(loop.account.positions.keys()))>=RISK_CONFIG.max_positions_per_sector:diagnostics["sector_rejections"]+=1;continue
            if exceeds_correlation_limit(live.symbol,tuple(loop.account.positions.keys()),history,threshold=RISK_CONFIG.max_pairwise_correlation,window=RISK_CONFIG.correlation_window):diagnostics["correlation_rejections"]+=1;continue
            if live.symbol not in selected:selected.append(live.symbol)
            atr=max(live.price*max(live.volatility_pct,.05)/100*.5,live.price*.001);risk=None if tier=="A" else TIER_B_RISK_PCT
            result=loop.on_market({"symbol":live.symbol,"price":live.price,"direction":direction,"stop_distance":max(live.price*.006,atr*1.8,1e-8),"atr_distance":atr,"timestamp":None,"strategy_score":score,"strategy_tier":tier,"risk_pct_override":risk})
            if result.get("action")=="OPEN":diagnostics["opened_trades"]+=1;diagnostics[f"tier_{tier.lower()}_opened"]+=1
        diagnostics["closed_trades"]=loop.stats.closed_trades;diagnostics["peak_open_positions"]=max(diagnostics["peak_open_positions"],len(loop.account.positions));diagnostics["quarantined_symbols"]=sorted(quarantined);remaining=duration_seconds-(clock()-started)
        if remaining<=0:break
        sleep(min(interval_seconds,remaining))
    diagnostics.update(_audit_diagnostics(loop.account.audit_log));return MultiAssetPaperResult(duration_seconds//60,len(symbols),cycles,successful,errors,tuple(selected),loop.summary(mark_price=None),diagnostics)
