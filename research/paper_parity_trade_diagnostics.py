"""Trade-level diagnostics for the paper-parity replay.

This intentionally reuses the existing replay unchanged and captures the
PaperAccount audit log. It reports per-trade direction/symbol/score/exit and
cost-risk fields, plus partial-profit-aware expectancy diagnostics.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

import research.paper_parity_replay as replay
from paper_engine import PaperAccount as _PaperAccount


class CapturingPaperAccount(_PaperAccount):
    instances: list["CapturingPaperAccount"] = []

    def __post_init__(self) -> None:
        super().__post_init__()
        self.instances.append(self)


def _trade_records(audit_log: list[dict]) -> list[dict]:
    active: dict[str, dict] = {}
    records: list[dict] = []
    for event in audit_log:
        symbol = str(event.get("symbol", "")).upper()
        kind = event.get("event")
        if kind == "OPEN":
            active[symbol] = {
                "symbol": symbol,
                "direction": event.get("direction"),
                "entry_timestamp": event.get("timestamp"),
                "entry_price": event.get("price"),
                "quantity": event.get("quantity"),
                "strategy_score": event.get("strategy_score"),
                "strategy_tier": event.get("strategy_tier"),
                "risk_amount": event.get("risk_amount"),
                "initial_stop_price": event.get("initial_stop_price"),
                "target_price": event.get("target_price"),
                "partial_count": 0,
                "partial_pnl": 0.0,
            }
        elif kind == "PARTIAL_CLOSE" and symbol in active:
            active[symbol]["partial_count"] += 1
            active[symbol]["partial_pnl"] += float(event.get("pnl", 0.0) or 0.0)
        elif kind == "CLOSE" and symbol in active:
            trade = active.pop(symbol)
            trade.update({
                "exit_timestamp": event.get("timestamp"),
                "exit_price": event.get("price"),
                "exit_reason": event.get("reason"),
                "close_pnl": float(event.get("pnl", 0.0) or 0.0),
                "gross_pnl": float(event.get("gross_pnl", 0.0) or 0.0),
                "entry_fee": float(event.get("entry_fee", 0.0) or 0.0),
                "exit_fee": float(event.get("exit_fee", 0.0) or 0.0),
                "initial_stop_gap_pct": float(event.get("initial_stop_gap_pct", 0.0) or 0.0),
                "execution_gap_pct": float(event.get("execution_gap_pct", 0.0) or 0.0),
                "actual_loss_amount": float(event.get("actual_loss_amount", 0.0) or 0.0),
                "risk_to_actual_ratio": float(event.get("risk_to_actual_ratio", 0.0) or 0.0),
            })
            trade["total_trade_pnl"] = trade["partial_pnl"] + trade["close_pnl"]
            records.append(trade)
    return records


def _pf(values: list[float]) -> float:
    gains = sum(v for v in values if v > 0)
    losses = -sum(v for v in values if v < 0)
    return gains / losses if losses else (float("inf") if gains else 0.0)


def _aggregate(records: list[dict], key: str) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[str(record.get(key))].append(record)
    result = []
    for name, rows in sorted(groups.items()):
        pnls = [float(r["total_trade_pnl"]) for r in rows]
        result.append({
            key: name,
            "trades": len(rows),
            "wins": sum(p > 0 for p in pnls),
            "win_rate_pct": round(sum(p > 0 for p in pnls) / len(pnls) * 100, 4),
            "total_pnl": round(sum(pnls), 8),
            "avg_pnl": round(float(np.mean(pnls)), 8),
            "profit_factor": round(_pf(pnls), 8),
            "avg_risk_to_actual_ratio": round(float(np.mean([r["risk_to_actual_ratio"] for r in rows if r["risk_to_actual_ratio"] > 0])) if any(r["risk_to_actual_ratio"] > 0 for r in rows) else 0.0, 8),
        })
    return result


def diagnose(data_root: Path) -> dict:
    replay.CapturingPaperAccount = CapturingPaperAccount
    replay.PaperAccount = CapturingPaperAccount
    CapturingPaperAccount.instances.clear()
    frames = replay.load_dataset(data_root)
    modes = ("PAPER", "REGIME", "REGIME_BTC")
    output: dict = {"schema_version": 1, "procedure": "paper_parity_trade_diagnostics", "modes": {}}
    for mode in modes:
        before = len(CapturingPaperAccount.instances)
        summary, diagnostics = replay.run_replay(frames, mode)
        if len(CapturingPaperAccount.instances) <= before:
            raise RuntimeError(f"no PaperAccount captured for {mode}")
        account = CapturingPaperAccount.instances[-1]
        records = _trade_records(account.audit_log)
        close_pnls = [float(r["close_pnl"]) for r in records]
        total_pnls = [float(r["total_trade_pnl"]) for r in records]
        output["modes"][mode] = {
            "summary": summary,
            "replay_diagnostics": diagnostics,
            "closed_trade_records": len(records),
            "trade_pf_including_partials": round(_pf(total_pnls), 8),
            "trade_pnl_including_partials": round(sum(total_pnls), 8),
            "close_only_pf": round(_pf(close_pnls), 8),
            "partial_pnl_total": round(sum(float(r["partial_pnl"]) for r in records), 8),
            "direction": _aggregate(records, "direction"),
            "symbol": _aggregate(records, "symbol"),
            "exit_reason": _aggregate(records, "exit_reason"),
            "score": _aggregate(records, "strategy_score"),
            "trades": records,
        }
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = diagnose(Path(args.data))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "paper_parity_trade_diagnostics.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: {m: {"trades": v["closed_trade_records"], "pf_including_partials": v["trade_pf_including_partials"], "partial_pnl": v["partial_pnl_total"]} for m, v in report["modes"].items()} for k in ["modes"]}, indent=2))


if __name__ == "__main__":
    main()
