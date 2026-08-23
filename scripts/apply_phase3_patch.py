from pathlib import Path

path = Path("app.py")
text = path.read_text(encoding="utf-8")

marker = "\n\ndef strategy_discovery(\n"
if marker not in text:
    raise SystemExit("strategy_discovery marker not found")

helper = r'''

def make_walk_forward_folds(n, final_oos_fraction=0.20):
    """Return expanding chronological train/validation folds."""
    n = int(n)
    if n <= 0:
        return []

    oos_start = int(n * (1 - final_oos_fraction))
    if oos_start < 200:
        return []

    validation_size = max(50, int(oos_start * 0.15))
    first_validation_start = oos_start - validation_size * 3

    if first_validation_start < 100:
        validation_size = max(30, oos_start // 8)
        first_validation_start = oos_start - validation_size * 3

    if first_validation_start < 100:
        return []

    folds = []
    for index in range(3):
        valid_start = first_validation_start + index * validation_size
        valid_end = min(valid_start + validation_size, oos_start)
        if valid_start <= 0 or valid_end <= valid_start:
            continue
        folds.append((0, valid_start, valid_start, valid_end))

    return folds


def summarize_validation(results):
    """Aggregate chronological validation results."""
    if not results:
        return {
            "folds": 0,
            "profitable_folds": 0,
            "total_trades": 0,
            "avg_pf": 0.0,
            "avg_return": 0.0,
            "worst_dd": 0.0,
        }

    pfs = [
        min(float(r.get("pf", 0.0)), 3.0)
        if np.isfinite(float(r.get("pf", 0.0)))
        else 3.0
        for r in results
    ]
    returns = [float(r.get("return", 0.0)) for r in results]
    drawdowns = [float(r.get("dd", 0.0)) for r in results]

    return {
        "folds": len(results),
        "profitable_folds": sum(
            r.get("return", 0.0) > 0
            and r.get("pf", 0.0) >= 1.05
            for r in results
        ),
        "total_trades": sum(int(r.get("trades", 0)) for r in results),
        "avg_pf": float(np.mean(pfs)),
        "avg_return": float(np.mean(returns)),
        "worst_dd": float(np.min(drawdowns)),
    }
'''

if "def make_walk_forward_folds(" not in text:
    text = text.replace(marker, helper + marker, 1)

old = '''    validation_ranges = [
        (
            int(n * 0.35),
            int(n * 0.50),
        ),
        (
            int(n * 0.50),
            int(n * 0.65),
        ),
        (
            int(n * 0.65),
            int(n * 0.80),
        ),
    ]

    final_oos = data.iloc[
        int(n * 0.80):
    ].reset_index(drop=True)
'''
new = '''    validation_folds = make_walk_forward_folds(n)

    final_oos_start = int(n * 0.80)
    final_oos = data.iloc[
        final_oos_start:
    ].reset_index(drop=True)
'''
if old in text:
    text = text.replace(old, new, 1)

old_loop = '''            for start, end in validation_ranges:
                subset = data.iloc[
                    start:end
                ].reset_index(drop=True)

                result = run_backtest(
                    subset,
                    params,
                    mode,
                    capital,
                    risk,
                    fee,
                    slip,
                    direction,
                )

                folds.append(
                    result
                )
'''
new_loop = '''            for _train_start, _train_end, valid_start, valid_end in validation_folds:
                subset = data.iloc[
                    valid_start:valid_end
                ].reset_index(drop=True)

                result = run_backtest(
                    subset,
                    params,
                    mode,
                    capital,
                    risk,
                    fee,
                    slip,
                    direction,
                )

                folds.append(result)
'''
if old_loop in text:
    text = text.replace(old_loop, new_loop, 1)

old_stability = '''    validation_ranges = [
        (
            int(n * 0.35),
            int(n * 0.50),
        ),
        (
            int(n * 0.50),
            int(n * 0.65),
        ),
        (
            int(n * 0.65),
            int(n * 0.80),
        ),
    ]
'''
new_stability = '''    validation_folds = make_walk_forward_folds(n)
'''
if old_stability in text:
    text = text.replace(old_stability, new_stability, 1)

old_stability_loop = '''        for start, end in validation_ranges:
            subset = data.iloc[
                start:end
            ].reset_index(drop=True)
'''
new_stability_loop = '''        for _train_start, _train_end, valid_start, valid_end in validation_folds:
            subset = data.iloc[
                valid_start:valid_end
            ].reset_index(drop=True)
'''
if old_stability_loop in text:
    text = text.replace(old_stability_loop, new_stability_loop, 1)

path.write_text(text, encoding="utf-8")
