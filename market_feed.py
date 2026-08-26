"""Exchange market-data adapter for safe paper trading.

Read-only public market-data adapter. No authenticated endpoints or order
submission are implemented here.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    price: float
    timestamp: Optional[str] = None


class BinancePublicFeed:
    BASE_URL = "https://api.binance.com/api/v3/ticker/price"

    def __init__(self, timeout: float = 10.0, base_url: Optional[str] = None):
        self.timeout = timeout
        self.base_url = (base_url or self.BASE_URL).rstrip("/")

    def snapshot(self, symbol: str) -> MarketSnapshot:
        symbol = symbol.upper()
        request = Request(
            f"{self.base_url}?symbol={symbol}",
            headers={
                "User-Agent": "CryptoDayTrader-Paper/1.0",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"market feed HTTP {exc.code} for {symbol}") from exc
        except URLError as exc:
            raise RuntimeError(f"market feed network error for {symbol}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError(f"market feed timeout for {symbol}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"market feed returned invalid JSON for {symbol}") from exc

        if not isinstance(payload, dict) or "price" not in payload:
            raise RuntimeError(f"market feed returned no price for {symbol}: {payload!r}")
        try:
            price = float(payload["price"])
        except (TypeError, ValueError):
            # Preserve the historical API contract: malformed numeric data is
            # a validation error, while transport/provider failures remain
            # RuntimeError for failover diagnostics.
            raise ValueError(f"market feed returned invalid price for {symbol}")
        if price <= 0:
            raise ValueError("market price must be positive")
        return MarketSnapshot(
            symbol=symbol,
            price=price,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
