"""Multi-asset crypto market scanner for paper trading.

The scanner uses a curated liquid universe, applies lightweight liquidity and
volatility gates, and ranks candidates without placing orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


DEFAULT_LIQUID_UNIVERSE: tuple[str, ...] = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "TRXUSDT",
    "SUIUSDT", "TONUSDT", "LTCUSDT", "BCHUSDT", "DOTUSDT",
    "NEARUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "ATOMUSDT",
    "UNIUSDT", "ETCUSDT", "XLMUSDT", "FILUSDT", "AAVEUSDT",
    "INJUSDT", "HBARUSDT", "MKRUSDT", "ALGOUSDT", "VETUSDT",
    "ICPUSDT", "QNTUSDT", "GRTUSDT", "SANDUSDT", "MANAUSDT",
    "AXSUSDT", "EGLDUSDT", "RUNEUSDT", "THETAUSDT", "SEIUSDT",
    "TIAUSDT", "JUPUSDT", "PEPEUSDT", "WIFUSDT", "FLOKIUSDT",
    "BONKUSDT", "RENDERUSDT", "TAOUSDT", "ENAUSDT", "PYTHUSDT",
)


@dataclass(frozen=True)
class AssetSnapshot:
    symbol: str
    price: float
    quote_volume: float
    change_pct: float = 0.0
    volatility_pct: float = 0.0


@dataclass(frozen=True)
class RankedCandidate:
    symbol: str
    score: float
    liquidity_score: float
    volatility_score: float
    momentum_score: float


def liquid_universe(symbols: Iterable[str] | None = None, *, max_assets: int = 50) -> tuple[str, ...]:
    if max_assets < 1:
        raise ValueError("max_assets must be positive")
    source = DEFAULT_LIQUID_UNIVERSE if symbols is None else tuple(symbols)
    result: list[str] = []
    seen: set[str] = set()
    for symbol in source:
        normalized = str(symbol).strip().upper()
        if not normalized or normalized in seen or not normalized.endswith("USDT"):
            continue
        seen.add(normalized); result.append(normalized)
        if len(result) >= max_assets:
            break
    return tuple(result)


def rank_assets(snapshots: Sequence[AssetSnapshot], *, min_quote_volume: float = 5_000_000.0,
                max_candidates: int = 5) -> list[RankedCandidate]:
    """Filter illiquid assets and rank liquid, moving opportunities.

    Liquidity remains a hard gate and contributes to ranking, but it no longer
    overwhelms short-term momentum/volatility. Scores are normalized around
    realistic intraday moves rather than raw percentage values.
    """
    if min_quote_volume < 0:
        raise ValueError("min_quote_volume must be non-negative")
    if max_candidates < 1:
        raise ValueError("max_candidates must be positive")
    eligible = [x for x in snapshots if x.price > 0 and x.quote_volume >= min_quote_volume]
    if not eligible:
        return []
    max_volume = max(x.quote_volume for x in eligible) or 1.0
    ranked: list[RankedCandidate] = []
    for item in eligible:
        liquidity = min(100.0, 100.0 * item.quote_volume / max_volume)
        volatility = min(100.0, max(0.0, abs(item.volatility_pct) / 0.50 * 100.0))
        momentum = min(100.0, max(0.0, abs(item.change_pct) / 1.00 * 100.0))
        score = 0.30 * liquidity + 0.30 * volatility + 0.40 * momentum
        ranked.append(RankedCandidate(item.symbol, round(score, 4), round(liquidity, 4),
                                      round(volatility, 4), round(momentum, 4)))
    ranked.sort(key=lambda item: (-item.score, item.symbol))
    return ranked[:max_candidates]
