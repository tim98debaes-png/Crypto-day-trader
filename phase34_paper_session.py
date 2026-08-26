"""Bounded live-market-data paper-session runner.

The runner uses the public read-only market feed and the existing paper
execution loop. It never places authenticated exchange orders. A bounded
session is used so operational tests are repeatable and cannot run forever.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from market_feed import BinancePublicFeed
from paper_engine import PaperAccount
from paper_execution import PaperExecutionLoop
from candidate_registry import CandidateRegistry


@dataclass(frozen=True)
class PaperSessionResult:
    symbol: str
    samples: int
    last_price: float | None
    errors: int
    summary: dict


def run_bounded_paper_session(
    *,
    symbol: str,
    duration_seconds: int = 300,
    interval_seconds: int = 15,
    capital: float = 1000.0,
    feed=None,
    loop=None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> PaperSessionResult:
    """Run a bounded read-only market-data paper session.

    The caller supplies an already-approved registry-backed execution loop in
    production. Without an executable active candidate the loop safely waits.
    Feed errors are counted and do not create paper positions.
    """
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")

    feed = feed or BinancePublicFeed()
    loop = loop or PaperExecutionLoop(PaperAccount(capital=capital), registry=CandidateRegistry())
    started = clock()
    samples = 0
    errors = 0
    last_price = None

    while clock() - started < duration_seconds:
        try:
            snapshot = feed.snapshot(symbol)
            last_price = snapshot.price
            loop.on_market({
                "symbol": snapshot.symbol,
                "price": snapshot.price,
                "direction": "LONG",
                "stop_distance": max(snapshot.price * 0.01, 0.00000001),
                "timestamp": snapshot.timestamp,
            })
            samples += 1
        except Exception:
            errors += 1
        remaining = duration_seconds - (clock() - started)
        if remaining <= 0:
            break
        sleep(min(interval_seconds, remaining))

    return PaperSessionResult(
        symbol=symbol.upper(),
        samples=samples,
        last_price=last_price,
        errors=errors,
        summary=loop.summary(mark_price=last_price),
    )
