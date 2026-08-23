from pathlib import Path

path = Path("app.py")
text = path.read_text(encoding="utf-8")

# Use one canonical validation implementation shared by the optimizer and tests.
import_marker = "import streamlit as st\n"
import_line = "from validation_engine import (\n    make_walk_forward_folds,\n    summarize_validation,\n    validation_score,\n)\n"
if "from validation_engine import (" not in text:
    if import_marker not in text:
        raise SystemExit("streamlit import marker not found")
    text = text.replace(import_marker, import_marker + import_line, 1)

# Remove the temporary in-app helper implementation if an earlier patch inserted it.
helper_start = "\ndef make_walk_forward_folds(n, final_oos_fraction=0.20):\n"
strategy_marker = "\n\ndef strategy_discovery(\n"
if helper_start in text and strategy_marker in text:
    start = text.index(helper_start)
    end = text.index(strategy_marker, start)
    text = text[:start] + "\n" + text[end:]

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
    if not validation_folds:
        return {
            "Coin": symbol,
            "Status": "NO DATA",
            "Reason": "Te weinig data voor walk-forward validatie",
        }

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

old_score = '''            score = discovery_score(
                folds
            )
'''
new_score = '''            validation_summary = summarize_validation(
                folds
            )
            score = validation_score(
                validation_summary
            )
'''
if old_score in text:
    text = text.replace(old_score, new_score, 1)

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

required = [
    "from validation_engine import (",
    "validation_folds = make_walk_forward_folds(n)",
    "for _train_start, _train_end, valid_start, valid_end in validation_folds:",
    "score = validation_score(",
]
missing = [item for item in required if item not in text]
if missing:
    raise SystemExit("Phase 3 integration incomplete: " + ", ".join(missing))

path.write_text(text, encoding="utf-8")
