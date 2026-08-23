import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
app = importlib.import_module("app")


def test_validation_windows_are_strictly_forward_only():
    n = 1000
    # Phase 3 target convention: three expanding training windows followed
    # by immediately subsequent validation windows, with the final 20% held
    # out completely for OOS.
    final_oos_start = int(n * 0.80)
    folds = app.make_walk_forward_folds(n)

    assert len(folds) == 3
    previous_validation_end = 0
    for train_start, train_end, valid_start, valid_end in folds:
        assert train_start == 0
        assert train_end == valid_start
        assert valid_start < valid_end <= final_oos_start
        assert valid_start >= previous_validation_end
        previous_validation_end = valid_end


def test_oos_is_never_used_in_walk_forward_folds():
    n = 1000
    final_oos_start = int(n * 0.80)
    folds = app.make_walk_forward_folds(n)
    assert all(valid_end <= final_oos_start for _, _, _, valid_end in folds)


def test_validation_summary_is_stable_for_empty_input():
    summary = app.summarize_validation([])
    assert summary["folds"] == 0
    assert summary["profitable_folds"] == 0
    assert summary["total_trades"] == 0
