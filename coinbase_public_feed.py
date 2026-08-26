"""Read-only Coinbase public ticker adapter with symbol-aware fallback."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from market_feed import MarketSnapshot


class CoinbasePublicFeed:
    BASE_URL = "https://api.exchange.coinbase.com/products"

    def __init__(self, timeout: float = 10.0, base_url: str | None = None):
        self.timeout = timeout
        self.base_url = (base_url or self.BASE_URL).rstrip("/")

    @staticmethod
    def _products(symbol: str) -> tuple[str, ...]:
        base = symbol.upper().removesuffix("USDT")
        return (f"{base}-USD", f"{base}-USDC")

    def snapshot(self, symbol: str) -> MarketSnapshot:
        last_error: Exception | None = None
        for product in self._products(symbol):
            request = Request(
                f"{self.base_url}/{product}/ticker",
                headers={"User-Agent": "CryptoDayTrader-Paper/1.0", "Accept": "application/json"},
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                price = float(payload["price"])
                if price <= 0:
                    raise ValueError("market price must be positive")

                # Coinbase's ticker exposes base volume. Convert it to an
                # approximate quote volume using the current price.
                base_volume = float(payload.get("volume", 0.0))
                return MarketSnapshot(
                    symbol=symbol.upper(), price=price,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    quote_volume=max(0.0, base_volume * price),
                )
            except HTTPError as exc:
                last_error = RuntimeError(f"Coinbase feed HTTP {exc.code} for {product}")
            except (URLError, TimeoutError) as exc:
                last_error = RuntimeError(f"Coinbase feed network error for {product}: {exc}")
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                last_error = RuntimeError(f"Coinbase feed returned invalid data for {product}")
        raise last_error or RuntimeError(f"Coinbase feed unavailable for {symbol}")
