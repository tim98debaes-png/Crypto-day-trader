"""Conservative, data-independent asset and entry quality filters for Phase 5."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class AssetQuality:
    min_candles: int = 250
    min_volume_ratio: float = 0.20
    max_atr_pct: float = 0.08
    min_atr_pct: float = 0.0005

def asset_quality(row: dict, history_length: int, cfg: AssetQuality = AssetQuality()):
    if history_length < cfg.min_candles: return False, "insufficient_history"
    atr_pct=float(row.get("atr_pct",0) or 0); vol=float(row.get("vol_ratio",1) or 0)
    if atr_pct < cfg.min_atr_pct: return False, "too_low_volatility"
    if atr_pct > cfg.max_atr_pct: return False, "too_high_volatility"
    if vol < cfg.min_volume_ratio: return False, "weak_relative_volume"
    return True, "asset_quality_ok"

def entry_quality(diagnostics: dict, direction: str):
    if not diagnostics.get("trend"): return False, "trend_not_confirmed"
    checks=diagnostics.get("bounce_checks",{})
    required=("pullback_touch","ema_reclaim","directional_followthrough","pullback_structure")
    if sum(bool(checks.get(k)) for k in required) < 3: return False, "insufficient_bounce_confirmation"
    if not diagnostics.get("medium_momentum") or not diagnostics.get("short_momentum"): return False, "insufficient_momentum"
    if not diagnostics.get("microstructure"): return False, "weak_microstructure"
    return True, "entry_quality_ok"
