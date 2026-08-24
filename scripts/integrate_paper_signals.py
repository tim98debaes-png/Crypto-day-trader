"""Patch app.py so the existing live scanner uses the validated signal engine.

The patch is intentionally narrow: it preserves the existing indicator
calculation and only replaces the final raw signal decision with the shared
Phase-5 signal adapter. It fails closed if the expected source block changes.
"""

from pathlib import Path

APP = Path("app.py")

IMPORT_MARKER = "from validation_engine import (\n"
IMPORT_INSERT = "from signal_engine import generate_signal\n"

OLD = '''                if (\n                    long_value\n                    >= params["threshold"]\n                    and long_value\n                    > short_value\n                    + params["min_edge"]\n                ):\n                    raw_signal = "LONG"\n\n                elif (\n                    short_value\n                    >= params["threshold"]\n                    and short_value\n                    > long_value\n                    + params["min_edge"]\n                ):\n                    raw_signal = "SHORT"\n\n                else:\n                    raw_signal = "WAIT"\n\n                allowed = saved.get(\n                    "Status"\n                ) in {\n                    "ROBUST",\n                    "WATCH",\n                }\n\n                saved_direction = saved.get(\n                    "Direction"\n                )\n\n                if (\n                    allowed\n                    and raw_signal != "WAIT"\n                    and (\n                        not saved_direction\n                        or saved_direction\n                        == raw_signal\n                    )\n                ):\n                    signal = raw_signal\n                else:\n                    signal = "WAIT"\n'''

NEW = '''                candidate = dict(saved)\n                candidate["signal_threshold"] = params.get(\n                    "threshold", 70\n                )\n                candidate["rr"] = params.get(\n                    "rr", 2.0\n                )\n\n                signal_result = generate_signal(\n                    candidate,\n                    {\n                        "long_score": long_value,\n                        "short_score": short_value,\n                        "stop_distance": float(latest.atr)\n                        * float(params.get("sl_atr", 1.5)),\n                        "rr": float(params.get("rr", 2.0)),\n                    },\n                )\n\n                signal = signal_result.action\n\n                saved_direction = saved.get("Direction")\n                if (\n                    signal in {"LONG", "SHORT"}\n                    and saved_direction\n                    and saved_direction != signal\n                ):\n                    signal = "WAIT"\n'''


def main():
    text = APP.read_text(encoding="utf-8")

    if IMPORT_INSERT not in text:
        if IMPORT_MARKER not in text:
            raise SystemExit("validation_engine import marker not found")
        text = text.replace(IMPORT_MARKER, IMPORT_INSERT + IMPORT_MARKER, 1)

    count = text.count(OLD)
    if count == 0:
        if 'signal_result = generate_signal(' in text:
            return
        raise SystemExit("expected live-scanner signal block not found")
    if count != 1:
        raise SystemExit(f"expected one live-scanner signal block, found {count}")

    text = text.replace(OLD, NEW, 1)
    APP.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
