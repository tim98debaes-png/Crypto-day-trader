"""Bounded multi-asset public-feed paper session with research risk filters."""
from __future__ import annotations
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable
from entry_exit_logic import entry_signal, exit_signal
from multi_asset_scanner import AssetSnapshot, DEFAULT_LIQUID_UNIVERSE, RESEARCH_MIN_QUOTE_VOLUME, rank_assets
from paper_execution import PaperExecutionLoop
from strategy_risk_controls import RISK_CONFIG, exceeds_correlation_limit, sector_position_count

@dataclass(frozen=True)
class MultiAssetPaperResult:
    duration_minutes: int
    universe_size: int
    scan_cycles: int
    successful_snapshots: int
    feed_errors: int
    candidate_symbols: tuple[str, ...]
    summary: dict
    diagnostics: dict


def _ema(values: list[float], period: int) -> float | None:
    if not values: return None
    alpha = 2.0 / (period + 1.0); result = values[0]
    for value in values[1:]: result = alpha * value + (1.0 - alpha) * result
    return result


def _entry_score(prices: list[float]) -> tuple[int, dict[str, float]]:
    if len(prices) < 12: return 0, {}
    price=float(prices[-1]); fast=_ema(prices[-8:],5); slow=_ema(prices[-12:],10)
    if fast is None or slow is None: return 0, {}
    short=price/prices[-4]-1.0; medium=price/prices[-10]-1.0
    recent=[prices[i]/prices[i-1]-1.0 for i in range(len(prices)-3,len(prices))]
    positive=sum(1 for x in recent if x>0); negative=sum(1 for x in recent if x<0)
    score=sum((fast>=slow, price>=fast*0.999, medium>=0.0005, short>=0.0005, positive>=2))
    return score, {"short_return":short,"medium_return":medium,"positive_ticks":float(positive),"negative_ticks":float(negative),"fast":fast,"slow":slow}


def run_multi_asset_paper_session(*, feed, loop: PaperExecutionLoop, duration_seconds: int = 3600,
    interval_seconds: int = 30, universe: tuple[str, ...] = DEFAULT_LIQUID_UNIVERSE,
    sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> MultiAssetPaperResult:
    if duration_seconds <= 0 or interval_seconds <= 0: raise ValueError("duration_seconds and interval_seconds must be positive")
    symbols=tuple(dict.fromkeys(str(s).upper() for s in universe if s))
    if not symbols: raise ValueError("universe must not be empty")
    started=clock(); cycles=successful=errors=0; selected:list[str]=[]
    history={s:deque(maxlen=max(20,RISK_CONFIG.correlation_window+12)) for s in symbols}; failure_streak={s:0 for s in symbols}; quarantined:set[str]=set()
    diagnostics={"assets_attempted":0,"liquidity_rejections":0,"ranked_candidates":0,"entry_momentum_rejections":0,"entry_volatility_rejections":0,
                 "entry_trend_rejections":0,"entry_overextension_rejections":0,"entry_reversal_rejections":0,"market_regime_rejections":0,
                 "correlation_rejections":0,"sector_rejections":0,"position_cap_rejections":0,"entry_ready":0,"opened_trades":0,"closed_trades":0,
                 "signal_exits":0,"peak_open_positions":0,"research_gate_rejections":0,"quarantined_symbols":[]}
    while clock()-started < duration_seconds:
        cycles+=1; snapshots:list[AssetSnapshot]=[]; diagnostics["assets_attempted"]+=len(symbols)-len(quarantined)
        for symbol in tuple(loop.account.positions.keys()):
            try:
                snap=feed.snapshot(symbol); prices=history[symbol]; prices.append(float(snap.price)); atr_distance=max(float(snap.price)*max(float(getattr(snap,"volatility_pct",0.0)),0.05)/100.0*0.5,float(snap.price)*0.001)
                result=loop.on_market({"symbol":snap.symbol,"price":snap.price,"direction":loop.account.positions[symbol].direction,"stop_distance":max(snap.price*0.006,atr_distance*1.8,1e-8),"atr_distance":atr_distance,"timestamp":snap.timestamp},exit_signal=exit_signal(list(prices)))
                if result.get("action")=="CLOSE" and result.get("reason")=="SIGNAL": diagnostics["signal_exits"]+=1
                successful+=1
            except Exception: errors+=1
        for symbol in symbols:
            if symbol in quarantined: continue
            try:
                snap=feed.snapshot(symbol); price=float(snap.price); failure_streak[symbol]=0; prices=history[symbol]; prices.append(price)
                change_pct=((price/prices[0])-1.0)*100.0 if len(prices)>=3 else 0.0; moves=[abs((prices[i]/prices[i-1]-1.0)*100.0) for i in range(1,len(prices))]
                snapshots.append(AssetSnapshot(symbol,price,float(getattr(snap,"quote_volume",0.0)),change_pct,max(moves,default=0.0))); successful+=1
            except Exception:
                errors+=1; failure_streak[symbol]+=1
                if failure_streak[symbol]>=3: quarantined.add(symbol)
        diagnostics["liquidity_rejections"]+=sum(1 for item in snapshots if item.price<=0 or item.quote_volume<RESEARCH_MIN_QUOTE_VOLUME)
        ranked=rank_assets(snapshots,min_quote_volume=RESEARCH_MIN_QUOTE_VOLUME,max_candidates=10); diagnostics["ranked_candidates"]+=len(ranked)
        btc_prices=list(history.get("BTCUSDT",())); btc_ema=_ema(btc_prices,20) if len(btc_prices)>=5 else None; btc_trend_ok=btc_ema is None or btc_prices[-1]>=btc_ema
        entry_ready=[]
        for candidate in ranked:
            live=next(s for s in snapshots if s.symbol==candidate.symbol); prices=list(history[candidate.symbol]); score,features=_entry_score(prices)
            # Match the shared entry logic: require four of five confirmations,
            # including a meaningful current impulse, before deeper risk gates.
            if score < 4:
                diagnostics["entry_momentum_rejections"]+=1; continue
            if not (RISK_CONFIG.volatility_floor_pct<=live.volatility_pct<=RISK_CONFIG.volatility_ceiling_pct): diagnostics["entry_volatility_rejections"]+=1; continue
            if candidate.symbol!="BTCUSDT" and not btc_trend_ok: diagnostics["market_regime_rejections"]+=1; continue
            ready,reason=entry_signal(prices)
            if not ready:
                if reason=="trend_not_confirmed": diagnostics["entry_trend_rejections"]+=1
                elif reason=="overextended": diagnostics["entry_overextension_rejections"]+=1
                elif reason=="short_term_reversal": diagnostics["entry_reversal_rejections"]+=1
                else: diagnostics["entry_momentum_rejections"]+=1
                continue
            entry_ready.append(live)
        diagnostics["entry_ready"]+=len(entry_ready)
        for live in entry_ready:
            if live.symbol in loop.account.positions: continue
            if len(loop.account.positions)>=RISK_CONFIG.max_open_positions: diagnostics["position_cap_rejections"]+=1; continue
            if sector_position_count(live.symbol,tuple(loop.account.positions.keys()))>=RISK_CONFIG.max_positions_per_sector: diagnostics["sector_rejections"]+=1; continue
            if exceeds_correlation_limit(live.symbol,tuple(loop.account.positions.keys()),history,threshold=RISK_CONFIG.max_pairwise_correlation,window=RISK_CONFIG.correlation_window): diagnostics["correlation_rejections"]+=1; continue
            if live.symbol not in selected: selected.append(live.symbol)
            atr_distance=max(live.price*max(live.volatility_pct,0.05)/100.0*0.5,live.price*0.001)
            result=loop.on_market({"symbol":live.symbol,"price":live.price,"direction":"LONG","stop_distance":max(live.price*0.006,atr_distance*1.8,1e-8),"atr_distance":atr_distance,"timestamp":None})
            if result.get("action")=="OPEN": diagnostics["opened_trades"]+=1
            elif result.get("reason") in {"candidate_direction_mismatch","paper_monitor_blocked","paper_monitor_rollback_recovery","risk_control_block"}: diagnostics["research_gate_rejections"]+=1
        diagnostics["closed_trades"]=loop.stats.closed_trades; diagnostics["peak_open_positions"]=max(diagnostics["peak_open_positions"],len(loop.account.positions)); diagnostics["quarantined_symbols"]=sorted(quarantined)
        remaining=duration_seconds-(clock()-started)
        if remaining<=0: break
        sleep(min(interval_seconds,remaining))
    return MultiAssetPaperResult(duration_seconds//60,len(symbols),cycles,successful,errors,tuple(selected),loop.summary(mark_price=None),diagnostics)
