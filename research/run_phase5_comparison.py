"""Controlled Phase 5 comparison: C baseline vs independent filters."""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path
from .run_step2b_benchmark import load_rows,build_symbol_features,precompute_signals
from .legacy_strategy import candidate_grid
from .phase5_filters import asset_quality,entry_quality
from .portfolio_execution import run_portfolio

def variants(): return ('C_BASELINE','C_ASSET','C_ENTRY','C_BOTH')

def filtered_signal(signal,row,history_length,variant):
    if variant=='C_BASELINE' or signal.get('action') not in ('LONG','SHORT'): return signal
    if variant in ('C_ASSET','C_BOTH'):
        ok,_=asset_quality(row,history_length)
        if not ok: x=dict(signal); x['action']='WAIT'; return x
    if variant in ('C_ENTRY','C_BOTH'):
        ok,_=entry_quality(signal.get('diagnostics',{}),signal.get('action',''))
        if not ok: x=dict(signal); x['action']='WAIT'; return x
    return signal

def run_variant(features,maps,rows,variant):
    indices={s:0 for s in features}
    def provider(row):
        s=str(row['symbol']).upper(); i=indices[s]; indices[s]=i+1
        base=maps[s][i]['C']; return filtered_signal(base,row,i+1,variant)
    return run_portfolio(rows,provider)

def main():
 p=argparse.ArgumentParser(); p.add_argument('--data',required=True); p.add_argument('--output',required=True); a=p.parse_args()
 raw=load_rows(Path(a.data)); params=candidate_grid()[0]; features={}; maps={}; rows=[]
 for symbol,frame in raw.items():
  f=build_symbol_features(frame); f['symbol']=symbol; features[symbol]=f; maps[symbol]=precompute_signals(f,params); rows.extend(f.to_dict('records'))
 rows.sort(key=lambda r:(str(r['timestamp']),str(r['symbol']))); results={}
 for variant in variants(): results[variant]=run_variant(features,maps,rows,variant).summary()
 out=Path(a.output); out.mkdir(parents=True,exist_ok=True); report={'schema_version':2,'status':'PHASE5_COMPARISON_COMPLETE','variants':results,'baseline':'C_BASELINE'}; (out/'phase5_comparison.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
 with (out/'phase5_comparison.csv').open('w',newline='',encoding='utf-8') as h:
  fields=['variant','initial_capital','final_equity','pnl','return_pct','max_drawdown_pct','closed_trades','wins','losses','win_rate_pct','profit_factor']; w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); [w.writerow({'variant':k,**v}) for k,v in results.items()]
 print(json.dumps(report,indent=2,default=str))
if __name__=='__main__': main()
