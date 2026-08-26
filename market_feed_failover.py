"""Read-only public market-data failover adapter."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from market_feed import MarketSnapshot


@dataclass(frozen=True)
class FeedFailure:
    provider: str
    error_type: str
    error: str


class PublicFeedFailover:
    def __init__(self, feeds: Iterable[tuple[str, object]]):
        self.feeds = tuple(feeds)
        self.failures: list[FeedFailure] = []
        self.last_provider: str | None = None

    def snapshot(self, symbol: str) -> MarketSnapshot:
        self.failures.clear()
        for name, feed in self.feeds:
            try:
                snapshot = feed.snapshot(symbol)
                self.last_provider = name
                return snapshot
            except Exception as exc:
                self.failures.append(FeedFailure(name, type(exc).__name__, str(exc)))
        detail = "; ".join(f"{f.provider}: {f.error_type}: {f.error}" for f in self.failures)
        raise RuntimeError(f"all public market feeds failed: {detail}")
