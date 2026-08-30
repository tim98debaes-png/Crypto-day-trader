"""Run A/B/C benchmark and emit trade-level diagnostic artifacts."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from .run_step2b_benchmark import load_rows,build_symbol_features,precompute_signals,run_strategy
from .legacy_strategy import candidate_grid
from .phase4_export import export_result

def main():
 p=argparse.ArgumentParser(); p.add_argument('--data',required=True); p.add_argument('--start',required=True); p.add_argument('--end',required=True); p.add_argument('--output',required=True); a=p.parse_args()
 root=Path(a.data); out=Path(a.output); raw=load_rows(root); params=candidate_grid()[0]; features={}; maps={}; rows=[]
 for symbol,frame in raw.items():
  f=build_symbol_features(frame); f['symbol']=symbol; features[symbol]=f; maps[symbol]=precompute_signals(f,params); rows.extend(f.to_dict('records'))
 rows.sort(key=lambda r:(str(r['timestamp']),str(r['symbol'])))
 report={'schema_version':1,'status':'DIAGNOSTIC_EXECUTION_COMPLETE','start':a.start,'end':a.end,'strategies':{}}
 for strategy in ('A','B','C'):
  result=run_strategy(features,maps,strategy,rows); strategy_dir=out/strategy; diagnosis=export_result(result,strategy_dir); report['strategies'][strategy]={'label':{'A':'LEGACY','B':'CURRENT','C':'HYBRID'}[strategy],'summary':result.summary(),'diagnosis':diagnosis}
 out.mkdir(parents=True,exist_ok=True); (out/'phase4_report.json').write_text(json.dumps(report,indent=2,default=str)+'\n',encoding='utf-8'); print(json.dumps(report,indent=2,default=str))
if __name__=='__main__': main()
