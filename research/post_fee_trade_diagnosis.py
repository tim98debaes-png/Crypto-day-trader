"""Trade-level diagnosis for post-fee-sizing benchmark artifacts."""
from __future__ import annotations

import json
from pathlib import Path


def load_trades(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else data.get("trades", [])


def diagnose(trades: list[dict]) -> dict:
    def val(t, *keys, default=None):
        for k in keys:
            if k in t:
                return t[k]
        return default

    rows = []
    for t in trades:
        pnl = float(val(t, "pnl", "realized_pnl", default=0.0) or 0.0)
        side = str(val(t, "side", "direction", default="UNKNOWN")).upper()
        reason = str(val(t, "exit_reason", "close_reason", "result", default="UNKNOWN")).upper()
        risk = float(val(t, "risk_amount", default=0.0) or 0.0)
        rows.append((side, reason, pnl, risk))

    out = {"trades": len(rows), "total_pnl": sum(x[2] for x in rows), "by_side": {}, "by_exit": {}}
    for side, reason, pnl, risk in rows:
        d = out["by_side"].setdefault(side, {"trades": 0, "pnl": 0.0, "wins": 0})
        d["trades"] += 1; d["pnl"] += pnl; d["wins"] += pnl > 0
        d = out["by_exit"].setdefault(reason, {"trades": 0, "pnl": 0.0, "losses": 0})
        d["trades"] += 1; d["pnl"] += pnl; d["losses"] += pnl < 0
    return out
