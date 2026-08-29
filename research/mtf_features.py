"""Leakage-safe MTF feature builder matching the legacy research indicators."""
from __future__ import annotations
import pandas as pd
from app import indicators


def _base(df: pd.DataFrame) -> pd.DataFrame:
    x=df.copy()
    x["timestamp"]=pd.to_datetime(x["timestamp"],utc=True)
    x=x.sort_values("timestamp").drop_duplicates("timestamp")
    return indicators(x[["timestamp","open","high","low","close","volume"]].rename(columns={"timestamp":"time"}))


def _aggregate_ohlcv(base: pd.DataFrame, freq: str) -> pd.DataFrame:
    x=base.copy().set_index("time")
    grouped=x[["open","high","low","close","volume"]].resample(freq,origin="epoch",label="left",closed="left").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna().reset_index()
    return grouped


def _htf_available(frame: pd.DataFrame, suffix: str) -> pd.DataFrame:
    selected=frame[["time","close","ema20","ema50","ema200","rsi","macd_hist","adx","atr_pct","vol_ratio"]].copy()
    selected["available"]=selected["time"].shift(-1)
    selected=selected.dropna(subset=["available"])
    return selected.rename(columns={"close":f"close_{suffix}","ema20":f"ema20_{suffix}","ema50":f"ema50_{suffix}","ema200":f"ema200_{suffix}","rsi":f"rsi{suffix}","macd_hist":f"macd{suffix}","adx":f"adx{suffix}","atr_pct":f"atrpct{suffix}","vol_ratio":f"vol{suffix}"}).drop(columns=["time"])


def build_mtf_features(df5m: pd.DataFrame) -> pd.DataFrame:
    """Build 5m execution features plus only previously closed 15m/1h data."""
    d5=_base(df5m)
    d15=indicators(_aggregate_ohlcv(d5,"15min"))
    d1=indicators(_aggregate_ohlcv(d5,"1h"))
    out=pd.merge_asof(d5.sort_values("time"),_htf_available(d15,"15").sort_values("available"),left_on="time",right_on="available",direction="backward")
    out=pd.merge_asof(out.sort_values("time"),_htf_available(d1,"1h").sort_values("available"),left_on="time",right_on="available",direction="backward")
    required=["atr","adx","ema20_15","ema50_15","ema200_15","ema20_1h","ema50_1h","ema200_1h","rsi15","rsi1h","adx15","adx1h"]
    return out.dropna(subset=required).reset_index(drop=True)
