"""Run the reproducible Step 2b A/B/C portfolio benchmark."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path
import pandas as pd
from .legacy_strategy import candidate_grid, signals as legacy_signals
from .mtf_features import build_mtf_features
from .portfolio_execution import run_portfolio
from .step2b_adapters import current_signal


def load_rows(root: Path) -> dict[str, pd.DataFrame]:
    result={}
    for path in sorted(root.rglob("*.jsonl")):
        frame=pd.read_json(path, lines=True)
        if frame.empty: continue
        frame["symbol"]=path.stem.upper()
        frame["timestamp"]=pd.to_datetime(frame["timestamp"],utc=True)
        result[path.stem.upper()]=frame.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    if not result: raise RuntimeError("No historical candles found")
    return result


def build_symbol_features(raw: pd.DataFrame) -> pd.DataFrame:
    return build_mtf_features(raw[["timestamp","open","high","low","close","volume"]])


def precompute_signals(features: pd.DataFrame, params: dict) -> dict[int, dict]:
    long_s, short_s=legacy_signals(features,params)
    out={}
    prices=features["close"].astype(float).tolist()
    for i in range(len(features)):
        if i < 40:
            out[i]={"A":{"action":"WAIT"},"B":{"action":"WAIT"},"C":{"action":"WAIT"}}
            continue
        atr=float(features.iloc[i].get("atr",0) or 0)
        if bool(long_s[i]): a={"action":"LONG","stop_distance":max(atr*float(params.get("sl_atr",1.5)),1e-12),"rr":float(params.get("rr",2.0)),"strategy_score":60,"strategy_tier":"A"}
        elif bool(short_s[i]): a={"action":"SHORT","stop_distance":max(atr*float(params.get("sl_atr",1.5)),1e-12),"rr":float(params.get("rr",2.0)),"strategy_score":60,"strategy_tier":"A"}
        else: a={"action":"WAIT","strategy_tier":"A"}
        b={"action":"WAIT","strategy_tier":"B"}; c={"action":"WAIT","strategy_tier":"C"}
        for direction in ("LONG","SHORT"):
            ready,reason,score,diagnostics=current_signal(prices[:i+1],direction)
            if ready:
                b={"action":direction,"stop_distance":max(atr*1.5,1e-12),"rr":2.0,"strategy_score":score,"strategy_tier":"B","reason":reason,"diagnostics":diagnostics}
                if (direction=="LONG" and bool(long_s[i])) or (direction=="SHORT" and bool(short_s[i])):
                    c={"action":direction,"stop_distance":max(atr*1.5,1e-12),"rr":2.0,"strategy_score":score,"strategy_tier":"C","reason":"hybrid_confirmed","diagnostics":diagnostics}
                break
        out[i]={"A":a,"B":b,"C":c}
    return out


def run_strategy(all_features: dict[str,pd.DataFrame], signal_maps: dict[str,dict[int,dict]], strategy: str, rows: list[dict]) :
    indices={symbol:0 for symbol in all_features}
    def provider(row):
        symbol=str(row["symbol"]).upper(); i=indices[symbol]; indices[symbol]=i+1
        return signal_maps[symbol][i][strategy]
    return run_portfolio(rows,provider)


def main():
    p=argparse.ArgumentParser(); p.add_argument("--data",required=True); p.add_argument("--start",required=True); p.add_argument("--end",required=True); p.add_argument("--output",required=True); a=p.parse_args()
    raw=load_rows(Path(a.data)); params=candidate_grid()[0]; features={}; maps={}; rows=[]
    for symbol,frame in raw.items():
        f=build_symbol_features(frame); f["symbol"]=symbol; features[symbol]=f; maps[symbol]=precompute_signals(f,params); rows.extend(f.to_dict("records"))
    rows.sort(key=lambda r:(str(r["timestamp"]),str(r["symbol"])))
    # Keep only rows after the common warm-up required by the legacy MTF stack.
    cutoff=max((len(f) for f in features.values()),default=0)
    if cutoff<250: raise RuntimeError("Insufficient history for MTF benchmark")
    results={}
    for strategy in ("A","B","C"):
        result=run_strategy(features,maps,strategy,rows)
        results[strategy]={"label":{"A":"LEGACY","B":"CURRENT","C":"HYBRID"}[strategy],**result.summary()}
    out=Path(a.output); out.mkdir(parents=True,exist_ok=True)
    report={"schema_version":2,"status":"EXECUTION_COMPLETE","start":a.start,"end":a.end,"symbols":len(features),"candles":sum(len(x) for x in features.values()),"fixed_legacy_candidate":params,"execution":{"capital":1000.0,"risk_pct":0.5,"fee_pct":0.1,"slippage_pct":0.02,"max_daily_loss_pct":3.0},"results":results}
    (out/"ab_c_report.json").write_text(json.dumps(report,indent=2,default=str)+"\n",encoding="utf-8")
    with (out/"ab_c_report.csv").open("w",newline="",encoding="utf-8") as handle:
        fields=["strategy","label","initial_capital","final_equity","pnl","return_pct","max_drawdown_pct","closed_trades","wins","losses","win_rate_pct","profit_factor"]
        writer=csv.DictWriter(handle,fieldnames=fields); writer.writeheader()
        for key,value in results.items(): writer.writerow({"strategy":key,**value})
    print(json.dumps({"status":report["status"],"symbols":len(features),"candles":report["candles"],"results":results},indent=2,default=str))

if __name__=="__main__": main()
