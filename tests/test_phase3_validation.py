from pathlib import Path

from validation_engine import (
    assert_no_oos_leakage,
    make_walk_forward_folds,
    summarize_validation,
    validation_score,
)


def test_validation_windows_are_strictly_forward_only():
    n = 1000
    final_oos_start = int(n * 0.80)
    folds = make_walk_forward_folds(n)

    assert len(folds) == 3
    previous_validation_end = 0
    for train_start, train_end, valid_start, valid_end in folds:
        assert train_start == 0
        assert train_end == valid_start
        assert valid_start < valid_end <= final_oos_start
        assert valid_start >= previous_validation_end
        previous_validation_end = valid_end

    assert_no_oos_leakage(folds, n)


def test_oos_is_never_used_in_walk_forward_folds():
    n = 1000
    final_oos_start = int(n * 0.80)
    folds = make_walk_forward_folds(n)
    assert all(valid_end <= final_oos_start for _, _, _, valid_end in folds)


def test_validation_summary_is_stable_for_empty_input():
    summary = summarize_validation([])
    assert summary["folds"] == 0
    assert summary["profitable_folds"] == 0
    assert summary["total_trades"] == 0
    assert validation_score(summary) == 0.0


def test_validation_summary_and_score_reward_consistency():
    results = [
        {"pf": 1.50, "return": 8.0, "trades": 20, "dd": -8.0},
        {"pf": 1.30, "return": 5.0, "trades": 18, "dd": -10.0},
        {"pf": 1.20, "return": 3.0, "trades": 17, "dd": -12.0},
    ]
    summary = summarize_validation(results)
    assert summary["profitable_folds"] == 3
    assert summary["profitable_ratio"] == 1.0
    assert summary["total_trades"] == 55
    assert validation_score(summary) > 70.0


def test_optimizer_is_wired_to_shared_validation_engine():
    app_source = Path("app.py").read_text(encoding="utf-8")
    assert "from validation_engine import (" in app_source
    assert "validation_folds = make_walk_forward_folds(n)" in app_source
    assert "score = validation_score(" in app_source
    assert "for _train_start, _train_end, valid_start, valid_end in validation_folds:" in app_source
