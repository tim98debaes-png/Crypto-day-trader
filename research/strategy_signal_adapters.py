"""Portfolio-ready A/B/C adapters with one common signal schema."""
from __future__ import annotations
import numpy as np
from .legacy_strategy import signals as legacy_signals


def _legacy_at(data, params, i):
    long_s, short_s = legacy_signals(data.iloc[:i+1].copy(), params)
    return bool(long_s.iloc[-1] if hasattr(long_s,'iloc') else long_s[-1]), bool(short_s.iloc[-1] if hasattr(short_s,'iloc') else short_s[-1])


def make_provider(strategy, params=None):
    params=params or {"threshold":60,"min_edge":5}
    def provider(row, history):
        if strategy == 'A_LEGACY':
            if len(history) < 220: return {'action':'WAIT','strategy':'A'}
            long_ok, short_ok = _legacy_at(history, params, len(history)-1)
            if long_ok: return {'action':'LONG','strategy':'A','rr':2.0}
            if short_ok: return {'action':'SHORT','strategy':'A','rr':2.0}
            return {'action':'WAIT','strategy':'A'}
        from entry_exit_logic_v2 import entry_signal_details
        prices=history['close'].astype(float).tolist()
        current=[]
        for direction in ('LONG','SHORT'):
            ready, reason, score, diagnostics=entry_signal_details(prices,direction)
            if ready: current.append((score,direction,reason,diagnostics))
        if not current: return {'action':'WAIT','strategy':strategy}
        score,direction,reason,diagnostics=max(current)
        if strategy == 'B_CURRENT':
            return {'action':direction,'strategy':'B','score':score,'reason':reason,'diagnostics':diagnostics,'rr':2.0}
        # C: current setup plus legacy directional confirmation.
        long_ok,short_ok=_legacy_at(history,params,len(history)-1) if len(history)>=220 else (False,False)
        confirmed=(direction=='LONG' and long_ok) or (direction=='SHORT' and short_ok)
        return ({'action':direction,'strategy':'C','score':score,'reason':'hybrid_confirmed','diagnostics':diagnostics,'rr':2.0}
                if confirmed else {'action':'WAIT','strategy':'C','reason':'legacy_confirmation_failed'})
    return provider
