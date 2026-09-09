"""Leakage-safe MTF feature builder."""
from __future__ import annotations
import pandas as pd
from app import indicators


def _utc_ns(values):
    """Normalize timezone-aware timestamps to one merge-compatible dtype."""
    return pd.to_datetime(values, utc=True).dt.as_unit("ns")


def _base(df):
    x=df.copy(); x["timestamp"]=_utc_ns(x["timestamp"]); x=x.sort_values("timestamp").drop_duplicates("timestamp")
    return indicators(x[["timestamp","open","high","low","close","volume"]].rename(columns={"timestamp":"time"}))


def _aggregate_ohlcv(base,freq):
    x=base.copy().set_index("time")
    return x[["open","high","low","close","volume"]].resample(freq,origin="epoch",label="left",closed="left").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna().reset_index()


def _htf_available(frame,suffix):
    selected=frame[["time","close","ema20","ema50","ema200","rsi","macd_hist","adx","atr_pct","vol_ratio","vol_regime"]].copy(); selected["available"]=_utc_ns(selected["time"].shift(-1)); selected=selected.dropna(subset=["available"])
    return selected.rename(columns={"close":f"close_{suffix}","ema20":f"ema20_{suffix}","ema50":f"ema50_{suffix}","ema200":f"ema200_{suffix}","rsi":f"rsi{suffix}","macd_hist":f"macd{suffix}","adx":f"adx{suffix}","atr_pct":f"atrpct{suffix}","vol_ratio":f"vol{suffix}","vol_regime":f"vol_regime_{suffix}"}).drop(columns=["time"])


def build_mtf_features(df5m):
    d5=_base(df5m); d15=indicators(_aggregate_ohlcv(d5,"15min")); d1=indicators(_aggregate_ohlcv(d5,"1h"))
    out=pd.merge_asof(d5.sort_values("time"),_htf_available(d15,"15").sort_values("available"),left_on="time",right_on="available",direction="backward")
    out=pd.merge_asof(out.sort_values("time"),_htf_available(d1,"1h").sort_values("available"),left_on="time",right_on="available",direction="backward")
    required=["atr","adx","ema20_15","ema50_15","ema200_15","ema20_1h","ema50_1h","ema200_1h","rsi15","rsi1h","adx15","adx1h","vol_regime_1h"]
    out=out.dropna(subset=required).reset_index(drop=True)
    return out.rename(columns={"time":"timestamp"}) if "time" in out.columns else out


def add_btc_context(asset_features, btc_features):
    """Attach only closed BTC 1h context to asset 5m rows."""
    left=asset_features.copy(); left["timestamp"]=_utc_ns(left["timestamp"])
    right=btc_features[["timestamp","ema20_1h","ema50_1h","ema200_1h","adx1h","vol_regime_1h"]].copy()
    right["timestamp"]=_utc_ns(right["timestamp"])
    right=right.sort_values("timestamp").drop_duplicates("timestamp")
    right["available"]=_utc_ns(right["timestamp"].dt.floor("1h") + pd.Timedelta(hours=1))
    right=right.rename(columns={c:f"btc_{c}" for c in ["ema20_1h","ema50_1h","ema200_1h","adx1h","vol_regime_1h"]})
    return pd.merge_asof(left.sort_values("timestamp"),right.sort_values("available"),left_on="timestamp",right_on="available",direction="backward")
