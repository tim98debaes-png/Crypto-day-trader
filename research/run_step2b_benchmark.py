"""Execute the registered Step 2b A/B/C benchmark on captured OHLCV data.

The runner deliberately uses only information available before each candle.
It produces a machine-readable report and refuses to label incomplete runs as
successful benchmarks.
"""
from __future__ import annotations
import argparse, csv, json
from collections import defaultdict
from pathlib import Path
import pandas as pd
from .legacy_strategy import candidate_grid
from .step2b_adapters import legacy_scores, current_signal, hybrid_signal


def load_rows(root: Path):
    rows=[]
    for path in sorted(root.rglob("*.jsonl")):
        symbol=path.stem
        frame=pd.read_json(path, lines=True)
        if frame.empty: continue
        frame["symbol"]=symbol
        rows.append(frame)
    if not rows: raise RuntimeError("No historical candles found")
    return pd.concat(rows, ignore_index=True).sort_values(["timestamp","symbol"]).reset_index(drop=True)


def main():
    p=argparse.ArgumentParser(); p.add_argument("--data",required=True); p.add_argument("--start",required=True); p.add_argument("--end",required=True); p.add_argument("--output",required=True); a=p.parse_args()
    root=Path(a.data); out=Path(a.output); out.mkdir(parents=True,exist_ok=True)
    data=load_rows(root)
    if len(data)<100: raise RuntimeError("Insufficient historical data for benchmark")
    # A exact legacy scoring is evaluated on the captured per-symbol history.
    # B/C use the current causal price-window architecture. Execution metrics
    # are reported separately until the MTF portfolio adapter is connected.
    results=[]
    for symbol, frame in data.groupby("symbol", sort=True):
        prices=frame["close"].astype(float).tolist()
        if len(prices)<40: continue
        # Use a fixed legacy candidate from the registered grid: no optimizer
        # selection is performed on OOS data. The candidate is only a smoke
        # adapter here; full portfolio execution follows after MTF parity.
        params=candidate_grid()[0]
        try:
            scores=legacy_scores(frame,params)
            legacy_count=int(((scores[0]>=params["threshold"])|(scores[1]>=params["threshold"])).sum())
        except Exception as exc:
            raise RuntimeError(f"Legacy adapter failed for {symbol}: {exc}") from exc
        b_count=c_count=0
        for i in range(40,len(prices)):
            b=any(current_signal(prices[:i],d)[0] for d in ("LONG","SHORT"))
            if b: b_count+=1
            h=any(hybrid_signal(prices[:i], frame.iloc[i-1], d, 60, 0)[0] for d in ("LONG","SHORT"))
            if h: c_count+=1
        results.append({"symbol":symbol,"legacy_signal_bars":legacy_count,"current_signal_bars":b_count,"hybrid_signal_bars":c_count,"candles":len(frame)})
    if not results: raise RuntimeError("No symbol had enough history")
    report={"schema_version":1,"status":"SIGNAL_STAGE_COMPLETE_EXECUTION_STAGE_PENDING_MTF_PARITY","start":a.start,"end":a.end,"symbols":len(results),"results":results,"note":"Signal counts are not profitability results. Full A/B/C PnL requires MTF feature construction and portfolio execution parity."}
    (out/"ab_c_report.json").write_text(json.dumps(report,indent=2)+"\n")
    with (out/"ab_c_report.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=results[0].keys()); w.writeheader(); w.writerows(results)
    print(json.dumps({"status":report["status"],"symbols":len(results)},indent=2))

if __name__=="__main__": main()
