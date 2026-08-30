"""Download historical candles for the Phase 3 benchmark.

The downloader intentionally uses only the repository's public Binance REST
helper and writes a deterministic JSONL dataset plus manifest.
"""
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from multi_asset_scanner import liquid_universe
from research.historical_data import fetch_klines,save_jsonl

def main():
 p=argparse.ArgumentParser(); p.add_argument('--start',required=True); p.add_argument('--end',required=True); p.add_argument('--interval',default='5m'); p.add_argument('--max-assets',type=int,default=10); p.add_argument('--output',default='data/historical'); a=p.parse_args()
 root=Path(a.output); root.mkdir(parents=True,exist_ok=True); symbols=liquid_universe(max_assets=a.max_assets); files=[]
 for s in symbols:
  rows=fetch_klines(s,a.interval,a.start,a.end); path=root/f'{s}.jsonl'; save_jsonl(rows,path); files.append({'symbol':s,'path':str(path),'candles':len(rows)})
 manifest={'schema_version':2,'created_at':datetime.now(timezone.utc).isoformat(),'symbols':list(symbols),'interval':a.interval,'start':a.start,'end':a.end,'files':files,'strategies':['A_LEGACY','B_CURRENT','C_HYBRID'],'status':'DATASET_READY'}
 (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8'); print(json.dumps({'status':manifest['status'],'symbols':len(symbols),'files':len(files)},indent=2))
if __name__=='__main__': main()
