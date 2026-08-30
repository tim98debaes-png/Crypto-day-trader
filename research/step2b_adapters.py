"""A/B/C adapters for the Step 2b benchmark."""
from __future__ import annotations
import numpy as np
from .legacy_strategy import signals as legacy_signals
from entry_exit_logic_v2 import entry_signal_details

def legacy_scores(frame,params):
    long_score,short_score=legacy_signals(frame,params); return np.asarray(long_score),np.asarray(short_score)

def current_signal(prices,direction):
    return entry_signal_details(list(prices),direction)

def hybrid_signal(prices,frame_row,direction,legacy_score,legacy_other):
    ready,reason,score,diagnostics=current_signal(prices,direction)
    if not ready: return False,reason,score,diagnostics
    confirmed=legacy_score>legacy_other and legacy_score>=60
    if not confirmed: return False,"legacy_confirmation_failed",score,diagnostics
    diagnostics=dict(diagnostics); diagnostics["legacy_confirmation"]=True
    return True,"hybrid_confirmed",score,diagnostics
