"""Exchange market-data adapter for safe paper trading.

This adapter is read-only: it fetches public market data and emits normalized
snapshots. It contains no authenticated endpoints and cannot place orders.
"""

from dataclasses import dataclass
from typing import Optional
import json
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    price: float
    timestamp: Optional[str] = None


class BinancePublicFeed:
    BASE_URL = "https://api.binance.com/api/v3/ticker/price"

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def snapshot(self, symbol: str) -> MarketSnapshot:
        symbol = symbol.upper()
        request = Request(
            f"{self.BASE_URL}?symbol={symbol}",
            headers={"User-Agent": "CryptoDayTrader-Paper/1.0"},
        )
        with urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if "price" not in payload:
            raise RuntimeError(f"market feed returned no price for {symbol}")
        return MarketSnapshot(symbol=symbol, price=float(payload["price"]))
