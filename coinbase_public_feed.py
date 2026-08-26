"""Read-only Coinbase public ticker adapter."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from market_feed import MarketSnapshot


class CoinbasePublicFeed:
    BASE_URL = "https://api.exchange.coinbase.com/products/BTC-USD/ticker"

    def __init__(self, timeout: float = 10.0, base_url: str | None = None):
        self.timeout = timeout
        self.base_url = base_url or self.BASE_URL

    def snapshot(self, symbol: str) -> MarketSnapshot:
        request = Request(
            self.base_url,
            headers={
                "User-Agent": "CryptoDayTrader-Paper/1.0",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"Coinbase feed HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"Coinbase feed network error: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError("Coinbase feed timeout") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("Coinbase feed returned invalid JSON") from exc

        try:
            price = float(payload["price"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Coinbase feed returned invalid price: {payload!r}") from exc
        if price <= 0:
            raise ValueError("market price must be positive")
        return MarketSnapshot(
            symbol=symbol.upper(),
            price=price,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
