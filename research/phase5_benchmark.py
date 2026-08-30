"""Compare Phase 5 filters against the unchanged Phase 3 baseline."""
from __future__ import annotations
from .phase5_filters import asset_quality,entry_quality

def filter_signal(signal, row, history_length):
    if signal.get('action') not in ('LONG','SHORT'): return signal
    ok,reason=asset_quality(row,history_length)
    if not ok:
        x=dict(signal); x['action']='WAIT'; x['filter_reason']=reason; return x
    diagnostics=signal.get('diagnostics',{})
    ok,reason=entry_quality(diagnostics,signal['action'])
    if not ok:
        x=dict(signal); x['action']='WAIT'; x['filter_reason']=reason; return x
    return signal
