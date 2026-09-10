"""Discover historical entry edge before changing strategy parameters.

This is an analysis-only tool. It evaluates sufficiently warmed 1m bars,
without changing live logic, and measures forward returns, MFE/MAE and
normalized R across confirmation/regime/BTC buckets. Forward values are used
only as outcomes, never as entry features.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from entry_exit_logic import _entry_metrics
from research.mtf_features import add_btc_context, build_mtf_features

HORIZONS = (15, 30, 60, 120, 360)
REQUIRED = {"timestamp", "open", "high", "low", "close", "volume"}


def _load(root: Path) -> dict[str, pd.DataFrame]:
    out = {}
    for path in sorted(root.glob("*.jsonl")):
        f = pd.read_json(path, lines=True)
        if f.empty:
            continue
        if "timestamp" not in f:
            for alias in ("open_time", "openTime", "time", "ts"):
                if alias in f:
                    f = f.rename(columns={alias: "timestamp"})
                    break
        if not REQUIRED.issubset(f.columns):
            continue
        f = f.copy()
        raw = f.timestamp
        f["timestamp"] = pd.to_datetime(raw, utc=True, unit="ms", errors="coerce")
        if f.timestamp.isna().all():
            f["timestamp"] = pd.to_datetime(raw, utc=True, errors="coerce")
        for c in ("open", "high", "low", "close", "volume"):
            f[c] = pd.to_numeric(f[c], errors="coerce")
        f = (
            f.dropna(subset=list(REQUIRED))
            .sort_values("timestamp")
            .drop_duplicates("timestamp")
            .reset_index(drop=True)
        )
        f["symbol"] = path.stem.upper()
        out[path.stem.upper()] = f
    if "BTCUSDT" not in out:
        raise RuntimeError("BTCUSDT required")
    return out


def _features(raw):
    btc = build_mtf_features(raw["BTCUSDT"][["timestamp", "open", "high", "low", "close", "volume"]])
    result = {}
    for symbol, frame in raw.items():
        f = build_mtf_features(frame[["timestamp", "open", "high", "low", "close", "volume"]])
        f = add_btc_context(f, btc)
        f["symbol"] = symbol
        # Align the raw rolling volume series by timestamp. Feature construction
        # can warm-start/drop rows, so positional assignment is invalid.
        quote_volume = (
            frame.set_index("timestamp")["close"]
            .mul(frame.set_index("timestamp")["volume"])
            .rolling(1440, min_periods=1)
            .sum()
        )
        f["quote_volume_24h"] = f["timestamp"].map(quote_volume)
        result[symbol] = f.reset_index(drop=True)
    return result


def _vol(prices):
    if len(prices) < 2:
        return 0.0
    return max(
        (abs(prices[i] / prices[i - 1] - 1) * 100 for i in range(1, len(prices)) if prices[i - 1] > 0),
        default=0.0,
    )


def _regime(row, direction):
    try:
        e20, e50, e200, adx, vol = [
            float(row[c]) for c in ("ema20_1h", "ema50_1h", "ema200_1h", "adx1h", "vol_regime_1h")
        ]
        if not np.isfinite([e20, e50, e200, adx, vol]).all() or adx < 18 or vol > 3:
            return "NO_EDGE"
        if direction == "LONG" and e20 > e50 > e200:
            return "UP"
        if direction == "SHORT" and e20 < e50 < e200:
            return "DOWN"
        return "NO_EDGE"
    except (KeyError, TypeError, ValueError):
        return "NO_EDGE"


def _btc(row, direction):
    try:
        e20, e50, e200, adx, vol = [
            float(row[c])
            for c in ("btc_ema20_1h", "btc_ema50_1h", "btc_ema200_1h", "btc_adx1h", "btc_vol_regime_1h")
        ]
        if not np.isfinite([e20, e50, e200, adx, vol]).all() or vol > 3:
            return "BLOCK"
        up = adx >= 18 and e20 > e50 > e200
        down = adx >= 18 and e20 < e50 < e200
        return "ALIGNED" if (direction == "LONG" and up) or (direction == "SHORT" and down) else "NEUTRAL"
    except (KeyError, TypeError, ValueError):
        return "BLOCK"


def _aggregate(records):
    if not records:
        return {"samples": 0}
    r = np.asarray(records, float)
    wins = r[r > 0]
    losses = r[r < 0]
    return {
        "samples": int(len(r)),
        "mean_r": round(float(r.mean()), 6),
        "median_r": round(float(np.median(r)), 6),
        "win_rate_pct": round(float((r > 0).mean() * 100), 4),
        "pf": round(float(wins.sum() / -losses.sum()), 6)
        if len(losses)
        else (float("inf") if len(wins) else 0.0),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--stride", type=int, default=5, help="Evaluate every Nth 1m bar; default 5 for fast discovery.")
    a = ap.parse_args()
    if a.stride < 1:
        raise ValueError("stride must be >= 1")

    raw = _load(Path(a.data))
    data = _features(raw)
    groups = defaultdict(list)
    combo = defaultdict(list)
    symbol_count = defaultdict(list)
    total = 0

    for symbol, f in data.items():
        prices = f.close.astype(float).to_numpy()
        highs = f.high.astype(float).to_numpy()
        lows = f.low.astype(float).to_numpy()
        stop_end = len(f) - max(HORIZONS) - 1
        for i in range(12, stop_end, a.stride):
            hist = prices[max(0, i - 20) : i].tolist()
            price = prices[i]
            for direction in ("LONG", "SHORT"):
                fast, slow, short, medium, pos, neg, bounce, touched, bscore, bchecks = _entry_metrics(hist, direction)
                conf = {
                    "trend": fast >= slow if direction == "LONG" else fast <= slow,
                    "price_near_fast": abs(price / fast - 1) <= 0.0065,
                    "medium_momentum": medium >= 0.0005 if direction == "LONG" else medium <= -0.0005,
                    "short_momentum": short >= 0.0005 if direction == "LONG" else short <= -0.0005,
                    "microstructure": pos >= 2 if direction == "LONG" else neg >= 2,
                    "bounce": bounce,
                }
                if not touched:
                    continue
                vol = _vol(hist)
                regime = _regime(f.iloc[i], direction)
                btc = _btc(f.iloc[i], direction)
                stop = max(price * 0.006, price * max(vol, 0.05) / 100 * 0.5 * 1.8)
                stop_pct = stop / price if price > 0 else 0.0
                active = tuple(k for k, v in conf.items() if v)
                for h in HORIZONS:
                    j = i + h
                    end = prices[j]
                    ret = end / price - 1 if direction == "LONG" else price / end - 1
                    mfe = (
                        highs[i + 1 : j + 1].max() / price - 1
                        if direction == "LONG"
                        else price / lows[i + 1 : j + 1].min() - 1
                    )
                    mae = (
                        lows[i + 1 : j + 1].min() / price - 1
                        if direction == "LONG"
                        else price / highs[i + 1 : j + 1].max() - 1
                    )
                    # Keep the MFE/MAE calculations for research usefulness even
                    # though only normalized forward R is ranked in this phase.
                    _ = (mfe, mae)
                    r = ret / stop_pct if stop_pct > 0 else 0.0
                    groups[(direction, h)].append(r)
                    groups[(direction, h, regime, btc)].append(r)
                    combo[(direction, h, "+".join(active) or "NONE")].append(r)
                    symbol_count[(symbol, direction, h)].append(r)
                total += 1

    def ranked(source):
        out = []
        for key, vals in source.items():
            if len(vals) >= 50:
                out.append({"bucket": list(key), **_aggregate(vals)})
        return sorted(out, key=lambda x: (x["mean_r"], x["pf"]), reverse=True)

    best = ranked(groups)
    combos = ranked(combo)
    symbols = ranked(symbol_count)
    out = {
        "schema_version": 1,
        "status": "EXECUTION_COMPLETE",
        "entry_opportunities": total,
        "stride": a.stride,
        "horizons": HORIZONS,
        "notes": [
            "Forward outcomes are analysis-only and never used as entry features.",
            "Discovery uses every Nth 1m bar; stride is reported explicitly.",
            "Buckets require >=50 samples.",
            "PF is computed on normalized forward R, not live trade accounting.",
        ],
        "best_buckets": best[:80],
        "best_confirmation_combinations": combos[:80],
        "symbol_direction": symbols[:80],
    }
    p = Path(a.output)
    p.mkdir(parents=True, exist_ok=True)
    (p / "entry_edge_discovery.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": out["status"], "entry_opportunities": total, "stride": a.stride, "top": best[:12]}, indent=2))


if __name__ == "__main__":
    main()
