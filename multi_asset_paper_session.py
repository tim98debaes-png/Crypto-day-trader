"""Paper-only multi-asset session orchestration for Phase 35."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from multi_asset_scanner import AssetSnapshot, RankedCandidate, rank_assets


@dataclass(frozen=True)
class ScanResult:
    scanned: int
    eligible: int
    candidates: tuple[RankedCandidate, ...]


def scan_and_select(
    snapshots: Sequence[AssetSnapshot],
    *,
    min_quote_volume: float = 5_000_000.0,
    max_candidates: int = 5,
) -> ScanResult:
    """Rank the current market and return only eligible top candidates."""
    candidates = rank_assets(
        snapshots,
        min_quote_volume=min_quote_volume,
        max_candidates=max_candidates,
    )
    eligible = sum(
        1 for item in snapshots
        if item.price > 0 and item.quote_volume >= min_quote_volume
    )
    return ScanResult(len(snapshots), eligible, tuple(candidates))


def submit_paper_candidates(
    candidates: Iterable[RankedCandidate],
    submit: Callable[[str], None],
    *,
    max_positions: int = 1,
) -> tuple[str, ...]:
    """Send selected symbols to a caller-supplied paper executor only.

    The function intentionally accepts a callback rather than an exchange client,
    keeping this module incapable of placing real orders by itself.
    """
    if max_positions < 1:
        raise ValueError("max_positions must be positive")
    selected = []
    for candidate in candidates:
        if len(selected) >= max_positions:
            break
        submit(candidate.symbol)
        selected.append(candidate.symbol)
    return tuple(selected)
