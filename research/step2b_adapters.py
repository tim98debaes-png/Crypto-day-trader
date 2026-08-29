"""A/B/C adapters for the Step 2b benchmark.

A reproduces the legacy v8.5 score logic on an MTF dataframe. B uses the
current regime/setup/trigger architecture. C is deliberately a transparent
intersection: current architecture is the gate and legacy momentum/volume
confirmation can only confirm, never create, a signal.
"""
from __future__ import annotations

import numpy as np
from .legacy_strategy import make_signals


def legacy_scores(frame, params):
    long_score, short_score = make_signals(frame, params)
    return np.asarray(long_score), np.asarray(short_score)


def current_signal(prices, direction):
    from entry_exit_logic_v2 import entry_signal_details
    ready, reason, score, diagnostics = entry_signal_details(list(prices), direction)
    return ready, reason, score, diagnostics


def hybrid_signal(prices, frame_row, direction, legacy_score, legacy_other):
    ready, reason, score, diagnostics = current_signal(prices, direction)
    if not ready:
        return False, reason, score, diagnostics
    # Legacy confirmation is deliberately only a filter. It cannot manufacture
    # a trade when the current architecture rejects it.
    if direction == "LONG":
        confirmed = legacy_score > legacy_other and legacy_score >= 60
    else:
        confirmed = legacy_score > legacy_other and legacy_score >= 60
    if not confirmed:
        return False, "legacy_confirmation_failed", score, diagnostics
    diagnostics = dict(diagnostics)
    diagnostics["legacy_confirmation"] = True
    return True, "hybrid_confirmed", score, diagnostics
