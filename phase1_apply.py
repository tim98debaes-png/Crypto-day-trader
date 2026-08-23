from pathlib import Path

p = Path("app.py")
s = p.read_text(encoding="utf-8")

replacements = [
    ('APP_VERSION = "8.4.4"', 'APP_VERSION = "8.5.0"'),
    ('RESULTS_FILE = "optimizer_results_v844.json"', 'RESULTS_FILE = "optimizer_results_v850.json"'),
    ('def make_config(days, mode, capital, risk, fee, slip):\n    return {', 'def make_config(days, mode, capital, risk, fee, slip, optimizer_mode="Volledig"):\n    return {'),
    ('        "optimizer_mode": "Volledig",\n', '        "optimizer_mode": str(optimizer_mode),\n'),
    ('    candidates = []\n\n    for base in strategy_pool:', '    candidates = []\n\n    strategy_pool = (\n        STRATEGIES\n        if optimizer_mode == "Volledig"\n        else fast_strategy_pool()\n    )\n\n    for base in strategy_pool:'),
    ('        "max bars": params["max_bars"],\n    }', '        "max bars": params["max_bars"],\n        "Strategy Params": dict(params),\n    }'),
    ('        "max bars": row.get(\n            "max bars"\n        ),\n    }', '        "max bars": row.get(\n            "max bars"\n        ),\n        "Strategy Params": row.get(\n            "Strategy Params"\n        ),\n    }'),
    ('current_config = make_config(\n    days,\n    mode,\n    capital,\n    risk,\n    fee,\n    slip,\n)\ncurrent_config["optimizer_mode"] = optimizer_mode', 'current_config = make_config(\n    days,\n    mode,\n    capital,\n    risk,\n    fee,\n    slip,\n    optimizer_mode,\n)'),
    ('                    strategy_discovery(\n                        symbol,\n                        days,\n                        mode,\n                        capital,\n                        risk,\n                        fee,\n                        slip,\n                    )', '                    strategy_discovery(\n                        symbol,\n                        days,\n                        mode,\n                        capital,\n                        risk,\n                        fee,\n                        slip,\n                        optimizer_mode,\n                    )'),
]

for old, new in replacements:
    if old not in s:
        raise SystemExit(f"Patch marker not found: {old[:100]!r}")
    s = s.replace(old, new, 1)

old_scanner = '''                family = str(
                    saved.get(
                        "Strategy",
                        "TREND",
                    )
                ).lower()

                params = {
                    "family": family,
                    "direction": saved.get(
                        "Direction",
                        "LONG",
                    ),
                    "rsi_min": 52,
                    "rsi_max": 68,
                    "adx_min": 18,
                    "adx_htf": 18,
                    "vol_min": 1.0,
                    "vol_regime_min": 0.55,
                    "vol_regime_max": 2.8,
                    "slope_min": 0.02,
                    "sl_atr": float(
                        saved.get(
                            "SL ATR",
                            1.5,
                        )
                    ),
                    "rr": float(
                        saved.get(
                            "RR",
                            2.0,
                        )
                    ),
                    "threshold": int(
                        saved.get(
                            "threshold",
                            70,
                        )
                    ),
                    "min_edge": 5,
                    "max_bars": int(
                        saved.get(
                            "max bars",
                            48,
                        )
                    ),
                    "min_stop_pct": 0.35,
                    "trail_atr": 1.0,
                    "trail_trigger_r": 1.0,
                }
'''
new_scanner = '''                params = saved.get("Strategy Params")

                if not isinstance(params, dict):
                    scan_rows.append(
                        {
                            "Coin": symbol,
                            "Signal": "WAIT",
                            "Strategy": saved.get("Strategy", "-"),
                            "Long": 0,
                            "Short": 0,
                            "Reason": "Geen volledige geoptimaliseerde parameters opgeslagen; opnieuw optimaliseren vereist.",
                        }
                    )
                    continue

                params = dict(params)
                family = str(
                    params.get(
                        "family",
                        saved.get("Strategy", "TREND"),
                    )
                ).lower()
                params["family"] = family
                params["direction"] = saved.get(
                    "Direction",
                    params.get("direction", "LONG"),
                )
'''
if old_scanner not in s:
    raise SystemExit("Scanner parameter block not found")
s = s.replace(old_scanner, new_scanner, 1)

p.write_text(s, encoding="utf-8")
print("Phase 1 patch applied")
