from pathlib import Path
import base64

path = Path("app.py")
text = path.read_text(encoding="utf-8")

marker = "\n\ndef strategy_discovery(\n"
if marker not in text:
    raise SystemExit("strategy_discovery marker not found")

helper = base64.b64decode("CgpkZWYgbWFrZV93YWxrX2ZvcndhcmRfZm9sZHMobiwgZmluYWxfb29zX2ZyYWN0aW9uPTAuMjApOgogICAgIiIiUmV0dXJuIGV4cGFuZGluZyBjaHJvbm9sb2dpY2FsIHRyYWluL3ZhbGlkYXRpb24gZm9sZHMuXG5cblRoZSBmaW5hbCBPT1Mgc2VnbWVudCBpcyBuZXZlciBpbmNsdWRlZCBpbiBhbnkgdmFsaWRhdGlvbiBmb2xkLlxuIEVhY2ggdmFsaWRhdGlvbiBibG9jayBzdGFydHMgYWZ0ZXIgaXRzIHRyYWluaW5nIGJsb2NrLiIiIgogICAgbiA9IGludChuKQogICAgaWYgbiA8PSAwOgogICAgICAgIHJldHVybiBbXQogICAgb29zX3N0YXJ0ID0gaW50KG4gKiAoMSAtIGZpbmFsX29vc19mcmFjdGlvbikpCiAgICBpZiBvb3Nfc3RhcnQgPCAyMDA6CiAgICAgICAgcmV0dXJuIFtdCgogICAgdmFsaWRhdGlvbl9zaXplID0gbWF4KDUwLCBpbnQob29zX3N0YXJ0ICogMC4xNSkpCiAgICBmaXJzdF92YWxpZGF0aW9uX3N0YXJ0ID0gb29zX3N0YXJ0IC0gdmFsaWRhdGlvbl9zaXplICogMwoKICAgIGlmIGZpcnN0X3ZhbGlkYXRpb25fc3RhcnQgPCAxMDA6CiAgICAgICAgdmFsaWRhdGlvbl9zaXplID0gbWF4KDMwLCBvb3Nfc3RhcnQgLy8gOCkKICAgICAgICBmaXJzdF92YWxpZGF0aW9uX3N0YXJ0ID0gb29zX3N0YXJ0IC0gdmFsaWRhdGlvbl9zaXplICogMwoKICAgIGlmIGZpcnN0X3ZhbGlkYXRpb25fc3RhcnQgPCAxMDA6CiAgICAgICAgcmV0dXJuIFtdCgogICAgZm9sZHMgPSBbXQogICAgZm9yIGluZGV4IGluIHJhbmdlKDMpOgogICAgICAgIHZhbGlkX3N0YXJ0ID0gZmlyc3RfdmFsaWRhdGlvbl9zdGFydCArIGluZGV4ICogdmFsaWRhdGlvbl9zaXplCiAgICAgICAgdmFsaWRfZW5kID0gbWluKHZhbGlkX3N0YXJ0ICsgdmFsaWRhdGlvbl9zaXplLCBvb3Nfc3RhcnQpCiAgICAgICAgaWYgdmFsaWRfc3RhcnQgPCA9IDAgb3IgdmFsaWRfZW5kIDw9IHZhbGlkX3N0YXJ0OgogICAgICAgICAgICBjb250aW51ZQogICAgICAgIGZvbGRzLmFwcGVuZCgKICAgICAgICAgICAgKDAsIHZhbGlkX3N0YXJ0LCB2YWxpZF9zdGFydCwgdmFsaWRfZW5kKQogICAgICAgICkKCiAgICByZXR1cm4gZm9sZHMKCgpkZWYgc3VtbWFyaXplX3ZhbGlkYXRpb24ocmVzdWx0cyk6CiAgICAiIiJBZ2dyZWdhdGUgY2hyb25vbG9naWNhbCB2YWxpZGF0aW9uIHJlc3VsdHMuIiIiCiAgICBpZiBub3QgcmVzdWx0czoKICAgICAgICByZXR1cm4gewogICAgICAgICAgICAiZm9sZHMiOiAwLAogICAgICAgICAgICAicHJvZml0YWJsZV9mb2xkcyI6IDAsCiAgICAgICAgICAgICJ0b3RhbF90cmFkZXMiOiAwLAogICAgICAgICAgICAiYXZnX3BmIjogMC4wLAogICAgICAgICAgICAiYXZnX3JldHVybiI6IDAuMCwKICAgICAgICAgICAgIndvcnN0X2RkIjogMC4wLAogICAgICAgIH0KCiAgICBwZnMgPSBbCiAgICAgICAgbWluKGZsb2F0KHIuZ2V0KCJwZiIsIDAuMCkpLCAzLjApCiAgICAgICAgaWYgbnAuaXNmaW5pdGUoZmxvYXQoci5nZXQoInBmIiwgMC4wKSkpCiAgICAgICAgZWxzZSAzLjAKICAgICAgICBmb3IgciBpbiByZXN1bHRzCiAgICBdCiAgICByZXR1cm5zID0gWwogICAgICAgIGZsb2F0KHIuZ2V0KCJyZXR1cm4iLCAwLjApKQogICAgICAgIGZvciByIGluIHJlc3VsdHMKICAgIF0KICAgIGRyYXdkb3ducyA9IFsKICAgICAgICBmbG9hdChyLmdldCgiZGQiLCAwLjApKQogICAgICAgIGZvciByIGluIHJlc3VsdHMKICAgIF0KCiAgICByZXR1cm4gewogICAgICAgICJmb2xkcyI6IGxlbihyZXN1bHRzKSwKICAgICAgICAicHJvZml0YWJsZV9mb2xkcyI6IHN1bSgKICAgICAgICAgICAgci5nZXQoInJldHVybiIsIDAuMCkgPiAwCiAgICAgICAgICAgIGFuZCByLmdldCgi cGYiLCAwLjApID4=PIDEuMDUKICAgICAgICAgICAgZm9yIHIgaW4gcmVzdWx0cwogICAgICAgICksCiAgICAgICAgInRvdGFsX3RyYWRlcyI6IHN1bSgKICAgICAgICAgICAgaW50KHIuZ2V0KCJ0cmFkZXMiLCAwKSkKICAgICAgICAgICAgZm9yIHIgaW4gcmVzdWx0cwogICAgICAgICksCiAgICAgICAgImF2Z19wZiI6IGZsb2F0KG5wLm1lYW4ocGZzKSksCiAgICAgICAgImF2Z19yZXR1cm4iOiBmbG9hdChucC5tZWFuKHJldHVybnMpKSwKICAgICAgICAid29yc3RfZGQiOiBmbG9hdChucC5taW4oZHJhd2Rvd25zKSksCiAgICB9Cg==").decode("utf-8")

if "def make_walk_forward_folds(" not in text:
    text = text.replace(marker, helper + marker, 1)

old = """    validation_ranges = [
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
"""
new = """    validation_folds = make_walk_forward_folds(n)

    final_oos_start = int(n * 0.80)
    final_oos = data.iloc[
        final_oos_start:
    ].reset_index(drop=True)
"""
if old in text:
    text = text.replace(old, new, 1)

old_loop = """            for start, end in validation_ranges:
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
"""
new_loop = """            for _train_start, _train_end, valid_start, valid_end in validation_folds:
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
"""
if old_loop in text:
    text = text.replace(old_loop, new_loop, 1)

old_stability = """    validation_ranges = [
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
"""
new_stability = """    validation_folds = make_walk_forward_folds(n)
"""
if old_stability in text:
    text = text.replace(old_stability, new_stability, 1)

old_stability_loop = """        for start, end in validation_ranges:
            subset = data.iloc[
                start:end
            ].reset_index(drop=True)
"""
new_stability_loop = """        for _train_start, _train_end, valid_start, valid_end in validation_folds:
            subset = data.iloc[
                valid_start:valid_end
            ].reset_index(drop=True)
"""
if old_stability_loop in text:
    text = text.replace(old_stability_loop, new_stability_loop, 1)

path.write_text(text, encoding="utf-8")
