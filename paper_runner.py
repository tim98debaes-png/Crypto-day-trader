"""Safe polling runner for paper trading.

The runner only consumes the read-only public feed and passes snapshots into
the paper execution loop. Strategy candidates are still supplied by the
validated optimizer; no exchange credentials are read or used.
"""

import time
from paper_engine import PaperAccount
from paper_execution import PaperExecutionLoop
from market_feed import BinancePublicFeed


class PaperRunner:
    def __init__(self, symbol: str = "BTCUSDT", interval_seconds: int = 15):
        if interval_seconds < 1:
            raise ValueError("interval_seconds must be >= 1")
        self.symbol = symbol.upper()
        self.interval_seconds = interval_seconds
        self.feed = BinancePublicFeed()
        self.loop = PaperExecutionLoop(PaperAccount())

    def tick(self, candidate=None, direction="LONG", stop_distance=0.0, rr=2.0):
        snapshot = self.feed.snapshot(self.symbol)
        market = {
            "symbol": snapshot.symbol,
            "price": snapshot.price,
            "direction": direction,
            "stop_distance": stop_distance,
            "rr": rr,
            "timestamp": snapshot.timestamp,
        }
        if candidate is None:
            return self.loop.on_market(market)
        if stop_distance <= 0:
            raise ValueError("stop_distance must be positive when a candidate is supplied")
        return self.loop.on_market(market, candidate=candidate)

    def run(self, candidate_provider=None, max_ticks=None):
        ticks = 0
        while max_ticks is None or ticks < max_ticks:
            candidate = candidate_provider() if candidate_provider else None
            self.tick(candidate=candidate)
            ticks += 1
            if max_ticks is None or ticks < max_ticks:
                time.sleep(self.interval_seconds)
