"""Run reproducible baseline/regime/BTC portfolio benchmark."""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path
import numpy as np
import pandas as pd
from .legacy_strategy import candidate_grid,signals as legacy_signals
from .mtf_features import build_mtf_features,add_btc_context
from .portfolio_execution import run_portfolio

REQUIRED_COLUMNS={"open","high","low","close","volume"}


def _normalize_frame(path:Path)->pd.DataFrame:
    frame=pd.read_json(path,lines=True)
    if frame.empty:return frame
    if "timestamp" not in frame.columns:
        for alias in ("open_time","openTime","time","ts"):
            if alias in frame.columns: frame=frame.rename(columns={alias:"timestamp"}); break
    missing=REQUIRED_COLUMNS-set(frame.columns)
    if "timestamp" not in frame.columns or missing: raise RuntimeError(f"Invalid historical candle schema in {path}: missing timestamp={'timestamp' not in frame.columns}, columns={sorted(map(str,frame.columns))}")
    frame=frame.copy(); frame["symbol"]=path.stem.upper(); raw=frame["timestamp"]
    frame["timestamp"]=pd.to_datetime(raw,utc=True,unit="ms",errors="coerce")
    if frame["timestamp"].isna().all(): frame["timestamp"]=pd.to_datetime(raw,utc=True,errors="coerce")
    frame=frame.dropna(subset=["timestamp"])
    if frame.empty: raise RuntimeError(f"No valid timestamps found in {path}")
    return frame.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)


def load_rows(root:Path):
    result={}
    for path in sorted(root.rglob("*.jsonl")):
        frame=_normalize_frame(path)
        if not frame.empty: result[path.stem.upper()]=frame
    if not result: raise RuntimeError("No historical candles found")
    if "BTCUSDT" not in result: raise RuntimeError("BTCUSDT historical candles are required for BTC filter benchmark")
    return result


def build_symbol_features(raw):
    f=build_mtf_features(raw[["timestamp","open","high","low","close","volume"]]).copy()
    if "timestamp" not in f.columns:
        if "time" in f.columns:f=f.rename(columns={"time":"timestamp"})
        else:raise RuntimeError("MTF feature builder returned neither timestamp nor time")
    f["timestamp"]=pd.to_datetime(f["timestamp"],utc=True); return f


def _regime_masks(features):
    finite=np.isfinite(features[["ema20_1h","ema50_1h","ema200_1h","adx1h","vol_regime_1h"]].astype(float)).all(axis=1)
    up=finite&(features["vol_regime_1h"]<=3.0)&(features["adx1h"]>=18.0)&(features["ema20_1h"]>features["ema50_1h"])&(features["ema50_1h"]>features["ema200_1h"])
    down=finite&(features["vol_regime_1h"]<=3.0)&(features["adx1h"]>=18.0)&(features["ema20_1h"]<features["ema50_1h"])&(features["ema50_1h"]<features["ema200_1h"])
    return up.to_numpy(dtype=bool),down.to_numpy(dtype=bool)


def _btc_masks(features):
    cols=["btc_ema20_1h","btc_ema50_1h","btc_ema200_1h","btc_adx1h","btc_vol_regime_1h"]
    finite=np.isfinite(features[cols].astype(float)).all(axis=1)
    high=finite&(features["btc_vol_regime_1h"]>3.0)
    up=finite&~high&(features["btc_adx1h"]>=18.0)&(features["btc_ema20_1h"]>features["btc_ema50_1h"])&(features["btc_ema50_1h"]>features["btc_ema200_1h"])
    down=finite&~high&(features["btc_adx1h"]>=18.0)&(features["btc_ema20_1h"]<features["btc_ema50_1h"])&(features["btc_ema50_1h"]<features["btc_ema200_1h"])
    return up.to_numpy(dtype=bool),down.to_numpy(dtype=bool),high.to_numpy(dtype=bool)


def precompute_signals(features,params):
    long_s,short_s=legacy_signals(features,params); regime_up,regime_down=_regime_masks(features); btc_up,btc_down,btc_high=_btc_masks(features); out={}; prices=features["close"].astype(float).tolist()
    for i in range(len(features)):
        if i<40: out[i]={"A":{"action":"WAIT"},"B":{"action":"WAIT"},"C":{"action":"WAIT"}}; continue
        atr=float(features.iloc[i].get("atr",0) or 0); stop=max(atr*float(params.get("sl_atr",1.5)),1e-12); rr=float(params.get("rr",2.0))
        legacy_long=bool(long_s[i]); legacy_short=bool(short_s[i])
        regime_long=legacy_long and regime_up[i]; regime_short=legacy_short and regime_down[i]
        btc_long=regime_long and not btc_down[i] and not btc_high[i]; btc_short=regime_short and not btc_up[i] and not btc_high[i]
        def action(long_ok,short_ok):
            if long_ok:return {"action":"LONG","stop_distance":stop,"rr":rr,"strategy_score":60,"strategy_tier":"A"}
            if short_ok:return {"action":"SHORT","stop_distance":stop,"rr":rr,"strategy_score":60,"strategy_tier":"A"}
            return {"action":"WAIT","strategy_tier":"A"}
        out[i]={"A":action(legacy_long,legacy_short),"B":action(regime_long,regime_short),"C":action(btc_long,btc_short)}
    return out


def run_strategy(all_features,signal_maps,strategy,rows):
    indices={symbol:0 for symbol in all_features}
    def provider(row):
        symbol=str(row["symbol"]).upper(); i=indices[symbol]; indices[symbol]=i+1; return signal_maps[symbol][i][strategy]
    return run_portfolio(rows,provider)


def main():
    p=argparse.ArgumentParser(); p.add_argument("--data",required=True); p.add_argument("--start",required=True); p.add_argument("--end",required=True); p.add_argument("--output",required=True); a=p.parse_args()
    raw=load_rows(Path(a.data)); params=candidate_grid()[0]; features={}; maps={}; rows=[]
    btc=build_symbol_features(raw["BTCUSDT"])
    for symbol,frame in raw.items():
        f=build_symbol_features(frame); f["symbol"]=symbol; f=add_btc_context(f,btc); features[symbol]=f; maps[symbol]=precompute_signals(f,params); rows.extend(f.to_dict("records"))
    rows.sort(key=lambda r:(str(r["timestamp"]),str(r["symbol"])))
    if min((len(f) for f in features.values()),default=0)<250: raise RuntimeError("Insufficient history for MTF benchmark")
    results={}
    labels={"A":"BASELINE","B":"REGIME","C":"REGIME_BTC"}
    for strategy in ("A","B","C"):
        result=run_strategy(features,maps,strategy,rows); results[strategy]={"label":labels[strategy],**result.summary()}
    out=Path(a.output); out.mkdir(parents=True,exist_ok=True); report={"schema_version":3,"status":"EXECUTION_COMPLETE","start":a.start,"end":a.end,"symbols":len(features),"candles":sum(len(x) for x in features.values()),"fixed_legacy_candidate":params,"filters":{"regime":{"adx_min":18,"vol_regime_max":3.0,"directional_ema_order":True},"btc":{"blocks_opposite_trend":True,"blocks_high_vol":True,"adx_min":18}},"execution":{"capital":1000.0,"risk_pct":0.5,"fee_pct":0.1,"slippage_pct":0.02,"max_daily_loss_pct":3.0},"results":results}
    (out/"ab_c_report.json").write_text(json.dumps(report,indent=2,default=str)+"\n",encoding="utf-8")
    with (out/"ab_c_report.csv").open("w",newline="",encoding="utf-8") as h:
        fields=["strategy","label","initial_capital","final_equity","pnl","return_pct","max_drawdown_pct","closed_trades","wins","losses","win_rate_pct","profit_factor"]; w=csv.DictWriter(h,fieldnames=fields); w.writeheader()
        for key,value in results.items():w.writerow({"strategy":key,**value})
    print(json.dumps({"status":report["status"],"symbols":len(features),"candles":report["candles"],"results":results},indent=2,default=str))

if __name__=="__main__":main()
