"""Leakage-safe 5m/15m/1h feature construction for research.

Higher-timeframe values are computed only from candles that have fully closed
before the execution candle. The current 5m row itself is never included in a
15m/1h aggregate used by that row.
"""
from __future__ import annotations
import pandas as pd
import numpy as np


def _ohlcv(df):
    x=df.copy(); x['timestamp']=pd.to_datetime(x['timestamp'],utc=True); x=x.sort_values('timestamp').drop_duplicates('timestamp').set_index('timestamp')
    return x[['open','high','low','close','volume']].astype(float)


def _ema(s,n): return s.ewm(span=n,adjust=False,min_periods=n).mean()
def _rsi(s,n=14):
    d=s.diff(); up=d.clip(lower=0); dn=-d.clip(upper=0); au=up.ewm(alpha=1/n,adjust=False,min_periods=n).mean(); ad=dn.ewm(alpha=1/n,adjust=False,min_periods=n).mean(); return 100-(100/(1+au/ad.replace(0,np.nan)))
def _atr(x,n=14):
    pc=x.close.shift(1); tr=pd.concat([(x.high-x.low),(x.high-pc).abs(),(x.low-pc).abs()],axis=1).max(axis=1); return tr.ewm(alpha=1/n,adjust=False,min_periods=n).mean()


def _features(x, prefix=''):
    y=x.copy(); c=y.close
    y[f'{prefix}ema20']=_ema(c,20); y[f'{prefix}ema50']=_ema(c,50); y[f'{prefix}ema200']=_ema(c,200)
    y[f'{prefix}rsi14']=_rsi(c,14); y[f'{prefix}atr14']=_atr(y,14)
    fast=_ema(c,12); slow=_ema(c,26); y[f'{prefix}macd']=fast-slow; y[f'{prefix}macd_signal']=_ema(y[f'{prefix}macd'],9)
    y[f'{prefix}vol_sma20']=y.volume.rolling(20,min_periods=20).mean()
    return y


def build_mtf_features(df5m: pd.DataFrame) -> pd.DataFrame:
    """Return one row per closed 5m candle with 15m/1h closed-bar features."""
    base=_features(_ohlcv(df5m),'5m_')
    out=base.copy()
    for rule,prefix in [('15min','15m_'),('1h','1h_')]:
        agg=base[['open','high','low','close','volume']].resample(rule,label='right',closed='right').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
        f=_features(agg,prefix)
        # shift one completed higher-timeframe bar so the execution candle can
        # only see the previous closed HTF candle.
        f=f.shift(1)
        out=out.join(f.add_suffix('_htf'),how='left')
        out=out.ffill()
    return out.reset_index()
