"""Integrated Step 2b benchmark runner.

This module deliberately keeps data, strategy and execution boundaries explicit.
It emits no performance claim unless a complete historical dataset is supplied.
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from .mtf_features import build_mtf_features
from .portfolio_execution import run_portfolio


def load_symbol(path: str | Path) -> pd.DataFrame:
    rows=[json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    df=pd.DataFrame(rows)
    required={'timestamp','symbol','open','high','low','close','volume'}
    missing=required-set(df.columns)
    if missing: raise ValueError(f'missing columns: {sorted(missing)}')
    return df.sort_values('timestamp').reset_index(drop=True)


def _signal_from_row(row, history, strategy):
    # Strategy adapters consume only data up to the current execution candle.
    if strategy == 'B_CURRENT':
        from .step2b_adapters import current_signal
        for direction in ('LONG','SHORT'):
            ready, reason, score, diagnostics=current_signal(history, direction)
            if ready:
                return {'action':direction,'stop_distance':max(float(row.get('5m_atr14',0) or 0),1e-12),'rr':2.0,'strategy_score':score,'strategy_tier':'B','reason':reason}
        return {'action':'WAIT'}
    raise NotImplementedError(strategy)


def run_current(df: pd.DataFrame):
    features=build_mtf_features(df)
    prices=[]
    def provider(row):
        nonlocal prices
        prices.append(float(row['close']))
        return _signal_from_row(row, prices, 'B_CURRENT')
    return run_portfolio(features.to_dict('records'), provider)


def write_report(result, output: str | Path):
    target=Path(output); target.mkdir(parents=True,exist_ok=True)
    (target/'B_current.json').write_text(json.dumps(result.summary(),indent=2,default=str)+'\n',encoding='utf-8')
