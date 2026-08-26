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
    quote_volume: float = 0.0


class BinancePublicFeed:
    BASE_URL = "https://api.binance.com/api/v3/ticker/24hr"

    def __init__(self, timeout: float = 10.0, base_url: Optional[str] = None):
        self.timeout = timeout
        self.base_url = (base_url or self.BASE_URL).rstrip("/")

    def snapshot(self, symbol: str) -> MarketSnapshot:
        symbol = symbol.upper()
        request = Request(
            f"{self.base_url}?symbol={symbol}",
            headers={"User-Agent": "CryptoDayTrader-Paper/1.0", "Accept": "application/json"},
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

        if not isinstance(payload, dict):
            raise RuntimeError(f"market feed returned invalid payload for {symbol}: {payload!r}")

        # Binance /ticker/24hr uses lastPrice. The price fallback keeps the
        # adapter compatible with existing mocked/legacy feed responses.
        raw_price = payload.get("lastPrice", payload.get("price"))
        if raw_price is None:
            raise RuntimeError(f"market feed returned no price for {symbol}: {payload!r}")
        try:
            price = float(raw_price)
            quote_volume = float(payload.get("quoteVolume", 0.0))
        except (TypeError, ValueError):
            raise ValueError(f"market feed returned invalid numeric data for {symbol}")
        if price <= 0:
            raise ValueError("market price must be positive")
        return MarketSnapshot(
            symbol=symbol,
            price=price,
            timestamp=datetime.now(timezone.utc).isoformat(),
            quote_volume=max(0.0, quote_volume),
        )
