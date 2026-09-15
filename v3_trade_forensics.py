"""Trade-level diagnostics used to design exits and validate edge quality."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from statistics import mean
from typing import Mapping, Sequence


@dataclass(frozen=True)
class TradeForensics:
    direction: str
    entry: float
    exit: float
    stop_distance: float
    pnl: float
    mfe_r: float
    mae_r: float
    bars_to_mfe: int
    bars_to_mae: int
    bars_open: int
    exit_reason: str


def analyze_trade(
    direction: str,
    entry: float,
    exit_price: float,
    stop_distance: float,
    path: Sequence[float],
    exit_reason: str,
) -> TradeForensics:
    if entry <= 0 or stop_distance <= 0 or not path:
        raise ValueError("entry, stop_distance and path must be valid")
    signed = [((p - entry) / stop_distance if direction == "LONG" else (entry - p) / stop_distance) for p in path]
    pnl = signed[-1]
    mfe = max(signed)
    mae = min(signed)
    return TradeForensics(
        direction=direction,
        entry=entry,
        exit=exit_price,
        stop_distance=stop_distance,
        pnl=pnl,
        mfe_r=mfe,
        mae_r=mae,
        bars_to_mfe=signed.index(mfe),
        bars_to_mae=signed.index(mae),
        bars_open=len(path) - 1,
        exit_reason=exit_reason,
    )


def summarize(records: Sequence[TradeForensics]) -> dict:
    if not records:
        return {"trades": 0}
    winners = [r for r in records if r.pnl > 0]
    losers = [r for r in records if r.pnl <= 0]
    return {
        "trades": len(records),
        "wins": len(winners),
        "losses": len(losers),
        "win_rate_pct": len(winners) / len(records) * 100,
        "expectancy_r": mean(r.pnl for r in records),
        "mfe_r_mean": mean(r.mfe_r for r in records),
        "mae_r_mean": mean(r.mae_r for r in records),
        "winner_mfe_r_mean": mean(r.mfe_r for r in winners) if winners else 0.0,
        "loser_mfe_r_mean": mean(r.mfe_r for r in losers) if losers else 0.0,
        "winner_mae_r_mean": mean(r.mae_r for r in winners) if winners else 0.0,
        "loser_mae_r_mean": mean(r.mae_r for r in losers) if losers else 0.0,
        "median_bars_open": sorted(r.bars_open for r in records)[len(records)//2],
        "exit_reasons": {reason: sum(r.exit_reason == reason for r in records) for reason in sorted({r.exit_reason for r in records})},
    }


def to_dicts(records: Sequence[TradeForensics]) -> list[dict]:
    return [asdict(r) for r in records]
