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
from paper_session_controls import PaperSessionControl
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
        # Keep the historical default behaviour: a newly created paper session
        # is immediately runnable. Operators can pause/resume/stop explicitly.
        self.control = PaperSessionControl()

    @property
    def state(self) -> str:
        return self.control.state

    def start(self) -> str:
        return self.control.start()

    def resume(self) -> str:
        return self.control.resume()

    def pause(self) -> str:
        return self.control.pause()

    def stop(self) -> str:
        return self.control.stop()

    def status(self) -> dict:
        return self.control.snapshot()

    def tick(
        self,
        candidate_provider: CandidateProvider,
        indicator_provider: IndicatorProvider,
    ) -> dict:
        if not self.control.can_tick:
            return {
                symbol: {
                    "action": "WAIT",
                    "reason": self.control.state,
                    "session_state": self.control.state,
                }
                for symbol in self.symbols
            }

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
            result = self.runners[symbol].process(
                market, candidate or {}, indicators or {}
            )
            result["session_state"] = self.control.state
            results[symbol] = result
        return results

    def run(
        self,
        candidate_provider: CandidateProvider,
        indicator_provider: IndicatorProvider,
        max_ticks: Optional[int] = None,
    ) -> None:
        ticks = 0
        while max_ticks is None or ticks < max_ticks:
            if self.state == "STOPPED":
                break
            if self.state == "PAUSED":
                time.sleep(self.interval_seconds)
                continue
            self.tick(candidate_provider, indicator_provider)
            ticks += 1
            if max_ticks is None or ticks < max_ticks:
                time.sleep(self.interval_seconds)
