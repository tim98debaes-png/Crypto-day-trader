"""Stage-by-stage diagnostics for Strategy V2 entry conditions.

This is a diagnostic instrument, not an optimizer. It measures where the
independent V2 entry pipeline rejects otherwise eligible observations.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.paper_parity_replay import load_dataset
from research.strategy_v2_replay import _resample
from strategy_v2 import _atr, _closes, _ema, _field, _pullback_trigger, _relative_volume, _slope, _structure, generate_signal

REQUIRED_HISTORY = 50
WINDOW = 60


def _empty_direction() -> dict:
    return {
        "eligible": 0,
        "trend": 0,
        "structure": 0,
        "continuation": 0,
        "pullback_trigger": 0,
        "participation": 0,
        "btc_compatible": 0,
        "all_six": 0,
        "failed_at": {"trend": 0, "structure": 0, "pullback_trigger": 0, "participation": 0, "btc_compatible": 0},
        "score_distribution": {str(i): 0 for i in range(7)},
        "independent_pass_rates": {},
        "pullback_components": {"reclaim": 0, "impulse": 0, "depth": 0},
    }


def _pullback_components(candles: list[dict], direction: str, atr: float, ema_fast: float) -> tuple[bool, bool, bool, float]:
    if len(candles) < 5 or atr <= 0:
        return False, False, False, 0.0
    cur, prev = candles[-1], candles[-2]
    close, high, low, op = (_field(cur, "close"), _field(cur, "high"), _field(cur, "low"), _field(cur, "open"))
    pc, pl, ph = (_field(prev, "close"), _field(prev, "low"), _field(prev, "high"))
    lows = [_field(c, "low") for c in candles[-5:-1]]
    highs = [_field(c, "high") for c in candles[-5:-1]]
    if None in (close, high, low, op, pc, pl, ph) or any(v is None for v in lows + highs):
        return False, False, False, 0.0
    body = abs(close - op)
    if direction == "LONG":
        pb = min(v for v in lows if v is not None)
        reclaim = close > ema_fast and pc <= ema_fast
        impulse = close > max(v for v in highs if v is not None) and body / atr >= 0.30 and close > op
        depth = max(0.0, (ema_fast - pb) / atr)
    else:
        pb = max(v for v in highs if v is not None)
        reclaim = close < ema_fast and pc >= ema_fast
        impulse = close < min(v for v in lows if v is not None) and body / atr >= 0.30 and close < op
        depth = max(0.0, (pb - ema_fast) / atr)
    depth_ok = 0.15 <= depth <= 1.5
    return reclaim, impulse, depth_ok, depth


def _evaluate(c5: list[dict], c15: list[dict], c1: list[dict], btc1: list[dict] | None, direction: str) -> tuple[dict, int] | None:
    if min(len(c5), len(c15), len(c1)) < REQUIRED_HISTORY:
        return None
    x5, x15, x1 = _closes(c5), _closes(c15), _closes(c1)
    if not x5 or not x15 or not x1:
        return None
    e1f, e1s = _ema(x1, 20), _ema(x1, 50)
    e15f, e15s = _ema(x15, 20), _ema(x15, 50)
    e5f, atr5, rv = _ema(x5, 20), _atr(c5), _relative_volume(c5)
    s15, s1 = _slope(x15, 4), _slope(x1, 4)
    if None in (e1f, e1s, e15f, e15s, e5f, atr5, rv, s15, s1):
        return None
    structure, continuation = _structure(c15, direction)
    trigger, depth = _pullback_trigger(c5, direction, atr5, e5f)
    reclaim, impulse, depth_ok, _ = _pullback_components(c5, direction, atr5, e5f)
    trend = (e1f > e1s and e15f > e15s and s15 > 0 and s1 > 0) if direction == "LONG" else (e1f < e1s and e15f < e15s and s15 < 0 and s1 < 0)
    participation = rv >= 1.0
    btc_ok = True
    if btc1 is not None:
        xb = _closes(btc1)
        bf, bs = _ema(xb, 20), _ema(xb, 50)
        if bf is None or bs is None:
            return None
        btc_ok = (bf >= bs) if direction == "LONG" else (bf < bs)
    flags = [trend, structure, continuation, trigger, participation, btc_ok]
    return {"trend": trend, "structure": structure, "continuation": continuation, "pullback_trigger": trigger, "participation": participation, "btc_compatible": btc_ok, "reclaim": reclaim, "impulse": impulse, "depth_ok": depth_ok, "depth_atr": depth}, sum(flags)


def run_diagnostics(frames: dict[str, pd.DataFrame], stride: int = 1) -> dict:
    if "BTCUSDT" not in frames:
        raise ValueError("BTCUSDT is required for Strategy V2 diagnostics")
    bars = {symbol: {"5m": _resample(frame, "5min"), "15m": _resample(frame, "15min"), "1h": _resample(frame, "1h")} for symbol, frame in frames.items()}
    btc1m = bars["BTCUSDT"]["1h"]
    result = {"LONG": _empty_direction(), "SHORT": _empty_direction()}
    total_observations = 0
    invalid_observations = 0
    for symbol, symbol_bars in bars.items():
        if symbol == "BTCUSDT":
            continue
        f5, f15, f1 = symbol_bars["5m"], symbol_bars["15m"], symbol_bars["1h"]
        ts15 = f15["timestamp"].tolist()
        ts1 = f1["timestamp"].tolist()
        for i in range(REQUIRED_HISTORY, len(f5), stride):
            timestamp = f5.iloc[i]["timestamp"]
            total_observations += 1
            i15 = pd.Index(ts15).searchsorted(timestamp, side="left")
            i1 = pd.Index(ts1).searchsorted(timestamp, side="left")
            c5 = f5.iloc[max(0, i - WINDOW):i].to_dict("records")
            c15 = f15.iloc[max(0, i15 - WINDOW):i15].to_dict("records")
            c1 = f1.iloc[max(0, i1 - WINDOW):i1].to_dict("records")
            ib = pd.Index(btc1m["timestamp"].tolist()).searchsorted(timestamp, side="left")
            btc1 = btc1m.iloc[max(0, ib - WINDOW):ib].to_dict("records")
            if min(len(c5), len(c15), len(c1), len(btc1)) < REQUIRED_HISTORY:
                invalid_observations += 1
                continue
            for direction in ("LONG", "SHORT"):
                evaluated = _evaluate(c5, c15, c1, btc1, direction)
                if evaluated is None:
                    invalid_observations += 1
                    continue
                flags, score = evaluated
                d = result[direction]
                d["eligible"] += 1
                for key in ("trend", "structure", "continuation", "pullback_trigger", "participation", "btc_compatible"):
                    if flags[key]:
                        d[key] += 1
                for key, flag in (("reclaim", flags["reclaim"]), ("impulse", flags["impulse"]), ("depth", flags["depth_ok"])):
                    if flag:
                        d["pullback_components"][key] += 1
                d["score_distribution"][str(score)] += 1
                if all(flags[k] for k in ("trend", "structure", "continuation", "pullback_trigger", "participation", "btc_compatible")):
                    d["all_six"] += 1
                if not flags["trend"]:
                    d["failed_at"]["trend"] += 1
                elif not flags["structure"]:
                    d["failed_at"]["structure"] += 1
                elif not flags["pullback_trigger"]:
                    d["failed_at"]["pullback_trigger"] += 1
                elif not flags["participation"]:
                    d["failed_at"]["participation"] += 1
                elif not flags["btc_compatible"]:
                    d["failed_at"]["btc_compatible"] += 1
    for direction, d in result.items():
        eligible = d["eligible"]
        d["independent_pass_rates"] = {k: round(d[k] / eligible, 6) if eligible else 0.0 for k in ("trend", "structure", "continuation", "pullback_trigger", "participation", "btc_compatible")}
        d["pullback_component_pass_rates"] = {k: round(v / eligible, 6) if eligible else 0.0 for k, v in d["pullback_components"].items()}
        d["all_six_rate"] = round(d["all_six"] / eligible, 6) if eligible else 0.0
    parity_checks = 0
    parity_failures = 0
    for symbol, symbol_bars in bars.items():
        if symbol == "BTCUSDT":
            continue
        f5, f15, f1 = symbol_bars["5m"], symbol_bars["15m"], symbol_bars["1h"]
        ts15, ts1, tsb = f15["timestamp"].tolist(), f1["timestamp"].tolist(), btc1m["timestamp"].tolist()
        for i in range(REQUIRED_HISTORY, len(f5), max(stride, 5)):
            timestamp = f5.iloc[i]["timestamp"]
            i15, i1, ib = pd.Index(ts15).searchsorted(timestamp, side="left"), pd.Index(ts1).searchsorted(timestamp, side="left"), pd.Index(tsb).searchsorted(timestamp, side="left")
            c5, c15, c1, cb = (f5.iloc[max(0, i-WINDOW):i].to_dict("records"), f15.iloc[max(0, i15-WINDOW):i15].to_dict("records"), f1.iloc[max(0, i1-WINDOW):i1].to_dict("records"), btc1m.iloc[max(0, ib-WINDOW):ib].to_dict("records"))
            if min(len(c5), len(c15), len(c1), len(cb)) < REQUIRED_HISTORY:
                continue
            for direction in ("LONG", "SHORT"):
                evaluated = _evaluate(c5, c15, c1, cb, direction)
                if evaluated is None:
                    continue
                flags, score = evaluated
                if score != 6:
                    continue
                parity_checks += 1
                sig = generate_signal(c5, c15, c1, cb)
                if sig is None or sig.direction != direction:
                    parity_failures += 1
    return {"schema_version": 1, "status": "EXECUTION_COMPLETE", "procedure": "strategy_v2_entry_gate_diagnostics", "data_interval": "1m", "sampling": {"base_observation": "5m_closed_bar", "stride_5m": stride, "required_mtf_history": REQUIRED_HISTORY, "history_window": WINDOW}, "universe": [s for s in frames if s != "BTCUSDT"], "total_observations": total_observations, "invalid_observations": invalid_observations, "directions": result, "parity": {"all_six_cases_checked": parity_checks, "failures": parity_failures}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--stride", type=int, default=1)
    args = parser.parse_args()
    if args.stride < 1:
        raise SystemExit("--stride must be >= 1")
    report = run_diagnostics(load_dataset(Path(args.data)), stride=args.stride)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "strategy_v2_entry_diagnostics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
