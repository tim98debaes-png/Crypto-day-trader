"""Safe live-market paper session.

Reads public market prices and feeds them into the existing validated
paper-trading strategy runner. This module never reads exchange credentials
and never places exchange orders.
"""

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, Optional
import time

from market_feed import BinancePublicFeed, MarketSnapshot
from paper_engine import PaperAccount
from paper_execution import PaperExecutionLoop
from paper_strategy_runner import PaperStrategyRunner


CandidateProvider = Callable[[str, MarketSnapshot], Optional[dict]]
IndicatorProvider = Callable[[str, MarketSnapshot], dict]


@dataclass
class LivePaperSession:
    symbols: Iterable[str]
    interval_seconds: int = 60

    def __post_init__(self):
        self.symbols = tuple(symbol.upper() for symbol in self.symbols)
        if not self.symbols:
            raise ValueError("at least one symbol is required")
        if self.interval_seconds < 1:
            raise ValueError("interval_seconds must be >= 1")
        self.feed = BinancePublicFeed()
        self.accounts: Dict[str, PaperAccount] = {
            symbol: PaperAccount() for symbol in self.symbols
        }
        self.runners = {
            symbol: PaperStrategyRunner(PaperExecutionLoop(self.accounts[symbol]))
            for symbol in self.symbols
        }

    def tick(
        self,
        candidate_provider: CandidateProvider,
        indicator_provider: IndicatorProvider,
    ) -> dict:
        results = {}
        for symbol in self.symbols:
            snapshot = self.feed.snapshot(symbol)
            candidate = candidate_provider(symbol, snapshot)
            indicators = indicator_provider(symbol, snapshot)
            market = {
                "symbol": snapshot.symbol,
                "price": snapshot.price,
                "timestamp": snapshot.timestamp,
            }
            results[symbol] = self.runners[symbol].process(
                market, candidate or {}, indicators or {}
            )
        return results

    def run(
        self,
        candidate_provider: CandidateProvider,
        indicator_provider: IndicatorProvider,
        max_ticks: Optional[int] = None,
    ) -> None:
        ticks = 0
        while max_ticks is None or ticks < max_ticks:
            self.tick(candidate_provider, indicator_provider)
            ticks += 1
            if max_ticks is None or ticks < max_ticks:
                time.sleep(self.interval_seconds)
