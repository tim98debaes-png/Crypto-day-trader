"""Trade-level diagnostics for the Phase 3 A/B/C benchmark."""
from __future__ import annotations
from collections import Counter,defaultdict
import json
from pathlib import Path

def close_events(trades):
    return [e for e in trades if e.get('event')=='CLOSE']

def diagnose(trades):
    closes=close_events(trades); total=len(closes)
    by_symbol=defaultdict(lambda:{'trades':0,'wins':0,'losses':0,'pnl':0.0})
    by_direction=defaultdict(lambda:{'trades':0,'wins':0,'losses':0,'pnl':0.0})
    by_reason=defaultdict(lambda:{'trades':0,'wins':0,'losses':0,'pnl':0.0})
    tiers=defaultdict(lambda:{'trades':0,'wins':0,'losses':0,'pnl':0.0})
    for e in closes:
        pnl=float(e.get('pnl',0)); symbol=str(e.get('symbol','UNKNOWN')).upper(); direction=str(e.get('direction','UNKNOWN')).upper(); reason=str(e.get('reason','UNKNOWN')).upper(); tier=str(e.get('strategy_tier','UNKNOWN')).upper()
        for bucket,key in ((by_symbol,symbol),(by_direction,direction),(by_reason,reason),(tiers,tier)):
            bucket[key]['trades']+=1; bucket[key]['wins']+=int(pnl>0); bucket[key]['losses']+=int(pnl<0); bucket[key]['pnl']+=pnl
    def finalize(bucket):
        out={}
        for k,v in bucket.items():
            x=dict(v); x['pnl']=round(x['pnl'],8); x['win_rate_pct']=round(v['wins']/v['trades']*100,4) if v['trades'] else 0.0; out[k]=x
        return dict(sorted(out.items(),key=lambda kv:kv[1]['pnl']))
    wins=[float(e.get('pnl',0)) for e in closes if float(e.get('pnl',0))>0]; losses=[float(e.get('pnl',0)) for e in closes if float(e.get('pnl',0))<0]
    return {'trades':total,'wins':len(wins),'losses':len(losses),'gross_profit':round(sum(wins),8),'gross_loss':round(sum(losses),8),'avg_win':round(sum(wins)/len(wins),8) if wins else 0.0,'avg_loss':round(sum(losses)/len(losses),8) if losses else 0.0,'exit_reasons':dict(Counter(str(e.get('reason','UNKNOWN')).upper() for e in closes)),'by_symbol':finalize(by_symbol),'by_direction':finalize(by_direction),'by_exit_reason':finalize(by_reason),'by_strategy_tier':finalize(tiers)}

def diagnose_report(report_path: str|Path, output: str|Path):
    report=json.loads(Path(report_path).read_text(encoding='utf-8')); result={'schema_version':1,'source':str(report_path),'strategies':{}}
    for key,value in report.get('results',{}).items():
        result['strategies'][key]={'benchmark_summary':value,'diagnostic_note':'The benchmark summary does not retain individual trade events; rerun the benchmark with trade-level export enabled to populate full attribution.'}
    Path(output).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8'); return result
