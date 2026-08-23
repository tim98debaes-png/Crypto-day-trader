"""Phase 3 validation primitives.

Pure-Python, dependency-light helpers for chronological walk-forward
validation. The final OOS segment is explicitly excluded from all folds.
"""

from math import isfinite


def make_walk_forward_folds(
    n,
    final_oos_fraction=0.20,
    n_folds=3,
    min_train=100,
    min_validation=30,
):
    """Return expanding chronological (train_start, train_end, valid_start, valid_end) folds."""
    n = int(n)
    n_folds = int(n_folds)
    final_oos_fraction = float(final_oos_fraction)

    if n <= 0 or n_folds <= 0 or not 0 < final_oos_fraction < 1:
        return []

    oos_start = int(n * (1.0 - final_oos_fraction))
    available = oos_start - int(min_train)
    if available < n_folds * int(min_validation):
        return []

    validation_size = max(
        int(min_validation),
        available // n_folds,
    )
    first_validation_start = oos_start - validation_size * n_folds

    if first_validation_start < int(min_train):
        return []

    folds = []
    for index in range(n_folds):
        valid_start = first_validation_start + index * validation_size
        valid_end = min(valid_start + validation_size, oos_start)
        if valid_end <= valid_start:
            continue
        folds.append((0, valid_start, valid_start, valid_end))

    return folds


def assert_no_oos_leakage(folds, n, final_oos_fraction=0.20):
    """Raise ValueError if a fold touches the reserved final OOS segment."""
    n = int(n)
    oos_start = int(n * (1.0 - float(final_oos_fraction)))
    previous_end = 0

    for train_start, train_end, valid_start, valid_end in folds:
        if train_start != 0:
            raise ValueError("Walk-forward training must start at index 0")
        if train_end != valid_start:
            raise ValueError("Validation must begin where its training window ends")
        if valid_start < previous_end:
            raise ValueError("Validation windows must be chronological and non-overlapping")
        if valid_end > oos_start:
            raise ValueError("Validation window leaks into final OOS segment")
        previous_end = valid_end

    return True


def summarize_validation(results):
    """Aggregate validation results without allowing NaN/inf to dominate ranking."""
    if not results:
        return {
            "folds": 0,
            "profitable_folds": 0,
            "profitable_ratio": 0.0,
            "total_trades": 0,
            "avg_pf": 0.0,
            "avg_return": 0.0,
            "worst_dd": 0.0,
        }

    pfs = []
    returns = []
    drawdowns = []
    profitable = 0
    total_trades = 0

    for result in results:
        pf = float(result.get("pf", 0.0))
        if not isfinite(pf):
            pf = 3.0
        pfs.append(min(max(pf, 0.0), 3.0))

        ret = float(result.get("return", 0.0))
        dd = float(result.get("dd", 0.0))
        returns.append(ret if isfinite(ret) else 0.0)
        drawdowns.append(dd if isfinite(dd) else -100.0)
        total_trades += int(result.get("trades", 0))

        if ret > 0 and pf >= 1.05:
            profitable += 1

    return {
        "folds": len(results),
        "profitable_folds": profitable,
        "profitable_ratio": profitable / len(results),
        "total_trades": total_trades,
        "avg_pf": sum(pfs) / len(pfs),
        "avg_return": sum(returns) / len(returns),
        "worst_dd": min(drawdowns),
    }


def validation_score(summary):
    """Return a 0-100 robustness score for validation-only results."""
    if summary.get("folds", 0) <= 0:
        return 0.0

    consistency = min(max(float(summary.get("profitable_ratio", 0.0)), 0.0), 1.0)
    pf_component = min(max(float(summary.get("avg_pf", 0.0)) / 1.5, 0.0), 1.0)
    return_component = min(max(float(summary.get("avg_return", 0.0)) / 15.0, 0.0), 1.0)
    trade_component = min(max(float(summary.get("total_trades", 0)) / 45.0, 0.0), 1.0)
    dd_component = min(max((float(summary.get("worst_dd", 0.0)) + 20.0) / 20.0, 0.0), 1.0)

    return round(
        consistency * 40
        + pf_component * 25
        + return_component * 15
        + trade_component * 10
        + dd_component * 10,
        4,
    )
