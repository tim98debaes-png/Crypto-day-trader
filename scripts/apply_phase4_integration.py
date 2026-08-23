from pathlib import Path


path = Path("app.py")
text = path.read_text(encoding="utf-8")

marker = "# PHASE4_ROBUSTNESS_INTEGRATED"

old_import = '''from validation_engine (\n'''

# The exact import block is intentionally matched so a future app refactor
# fails loudly instead of silently applying a partial integration.
validation_import = '''from validation_engine import (\n    make_walk_forward_folds,\n    summarize_validation,\n    validation_score,\n)\n'''
robustness_import = validation_import + '''from robustness_engine import (\n    monte_carlo as phase4_monte_carlo,\n    robustness_score as phase4_robustness_score,\n)\n'''

if "phase4_monte_carlo" not in text:
    if validation_import not in text:
        raise SystemExit("validation import block not found")
    text = text.replace(validation_import, robustness_import, 1)

old_mc = '''        mc = monte_carlo_stats(\n            oos.get(\n                "pnls",\n                [],\n            ),\n            capital=capital,\n            simulations=(300 if optimizer_mode == "Snel" else 1000),\n        )\n\n        status, confidence, reason = (\n'''
new_mc = '''        mc = monte_carlo_stats(\n            oos.get(\n                "pnls",\n                [],\n            ),\n            capital=capital,\n            simulations=(300 if optimizer_mode == "Snel" else 1000),\n        )\n\n        phase4_returns = [\n            (float(pnl) / float(capital)) * 100.0\n            for pnl in oos.get("pnls", [])\n            if np.isfinite(pnl)\n        ]\n        phase4_mc = phase4_monte_carlo(\n            phase4_returns,\n            simulations=(300 if optimizer_mode == "Snel" else 1000),\n            seed=42,\n            initial_equity=capital,\n        )\n        phase4_mc_score = phase4_robustness_score(phase4_mc)\n\n        status, confidence, reason = (\n'''
if "phase4_mc_score" not in text:
    if old_mc not in text:
        raise SystemExit("optimizer Monte Carlo call block not found")
    text = text.replace(old_mc, new_mc, 1)

old_rank = '''        rank = (\n            1 if status == "TRADE" else 0,\n            confidence,\n            stability["score"],\n            (\n                oos["pf"]\n                if np.isfinite(\n                    oos["pf"]\n                )\n                else 3\n            ),\n            oos["return"],\n        )\n'''
new_rank = '''        rank = (\n            1 if status == "TRADE" else 0,\n            phase4_mc_score,\n            confidence,\n            stability["score"],\n            (\n                oos["pf"]\n                if np.isfinite(\n                    oos["pf"]\n                )\n                else 3\n            ),\n            oos["return"],\n        )\n'''
if "phase4_mc_score," not in text:
    if old_rank not in text:
        raise SystemExit("optimizer rank block not found")
    text = text.replace(old_rank, new_rank, 1)

old_output = '''        "MC P95 DD": (\n            round(\n                mc["p95_dd"],\n                2,\n            )\n            if np.isfinite(\n                mc["p95_dd"]\n            )\n            else np.nan\n        ),\n        "Reason": reason,\n'''
new_output = '''        "MC P95 DD": (\n            round(\n                mc["p95_dd"],\n                2,\n            )\n            if np.isfinite(\n                mc["p95_dd"]\n            )\n            else np.nan\n        ),\n        "MC Robustness": round(phase4_mc_score, 2),\n        "MC Profit Probability": (\n            round(phase4_mc["probability_profit"] * 100, 2)\n            if phase4_mc.get("status") == "OK"\n            else np.nan\n        ),\n        "MC Return P05": (\n            round(phase4_mc["terminal_return_p05"], 2)\n            if phase4_mc.get("status") == "OK"\n            else np.nan\n        ),\n        "MC DD P95": (\n            round(phase4_mc["max_drawdown_p95"], 2)\n            if phase4_mc.get("status") == "OK"\n            else np.nan\n        ),\n        "Reason": reason,\n'''
if '"MC Robustness"' not in text:
    if old_output not in text:
        raise SystemExit("optimizer output block not found")
    text = text.replace(old_output, new_output, 1)

if marker not in text:
    text = marker + "\n" + text

path.write_text(text, encoding="utf-8")
print("Phase 4 robustness integration applied")
