"""Multi-asset paper portfolio aggregation.

Simulation only. This module never places exchange orders.
The configured capital is shared across the selected symbols rather than
being duplicated per asset.
"""

from dataclasses import dataclass, field
from typing import Optional

from paper_engine import PaperAccount


@dataclass
class PaperPortfolio:
    # `capital` is total portfolio capital, not capital per coin.
    capital: float = 1000.0
    risk_pct: float = 0.5
    fee_pct: float = 0.1
    slippage_pct: float = 0.02
    max_daily_loss_pct: float = 3.0
    accounts: dict[str, PaperAccount] = field(default_factory=dict)
    coins: list[str] = field(default_factory=list)
    total_capital: Optional[float] = None
    equity_history: list[float] = field(default_factory=list)
    peak_equity: float = 0.0
    max_drawdown_pct: float = 0.0

    def __post_init__(self):
        # Keep compatibility with the original Phase-5 test/API naming.
        if self.total_capital is not None:
            self.capital = float(self.total_capital)
        self.capital = float(self.capital)
        if self.capital <= 0:
            raise ValueError("capital must be positive")
        self.coins = [str(symbol).upper() for symbol in self.coins]
        self.peak_equity = self.capital
        self.equity_history.append(self.capital)

    def _allocation(self) -> float:
        """Return equal total-capital allocation for each configured symbol."""
        count = len(self.coins)
        if count <= 0:
            # Backwards-compatible single-asset behaviour when no universe is set.
            return self.capital
        return self.capital / count

    def account(self, symbol: str) -> PaperAccount:
        symbol = symbol.upper()
        if self.coins and symbol not in self.coins:
            self.coins.append(symbol)
        if symbol not in self.accounts:
            allocation = self._allocation()
            self.accounts[symbol] = PaperAccount(
                capital=allocation,
                cash=allocation,
                risk_pct=self.risk_pct,
                fee_pct=self.fee_pct,
                slippage_pct=self.slippage_pct,
                max_daily_loss_pct=self.max_daily_loss_pct,
            )
        return self.accounts[symbol]

    def _record_equity(self, value: float) -> None:
        value = float(value)
        self.equity_history.append(value)
        self.peak_equity = max(self.peak_equity, value)
        if self.peak_equity > 0:
            drawdown = (self.peak_equity - value) / self.peak_equity * 100.0
            self.max_drawdown_pct = max(self.max_drawdown_pct, drawdown)

    def equity(self, marks: Optional[dict] = None) -> float:
        marks = marks or {}
        value = float(
            sum(
                account.equity(marks.get(symbol))
                for symbol, account in self.accounts.items()
            )
        )
        # Before the first account exists, the portfolio still owns all capital.
        if not self.accounts:
            value = self.capital
        self._record_equity(value)
        return value

    def audit_log(self) -> list:
        events = []
        for symbol, account in self.accounts.items():
            for event in account.audit_log:
                item = dict(event)
                item.setdefault("symbol", symbol)
                events.append(item)
        return sorted(events, key=lambda item: str(item.get("timestamp", "")))

    def summary(self, marks: Optional[dict] = None) -> dict:
        current_equity = self.equity(marks)
        events = self.audit_log()
        closes = [event for event in events if event.get("event") == "CLOSE"]
        wins = [event for event in closes if float(event.get("pnl", 0)) > 0]
        losses = [event for event in closes if float(event.get("pnl", 0)) < 0]
        gross_profit = sum(float(event.get("pnl", 0)) for event in wins)
        gross_loss = abs(sum(float(event.get("pnl", 0)) for event in losses))
        return_pct = (current_equity / self.capital - 1.0) * 100.0
        return {
            "equity": current_equity,
            "return_pct": return_pct,
            "peak_equity": self.peak_equity,
            "max_drawdown_pct": self.max_drawdown_pct,
            "symbols": len(self.accounts),
            "open_positions": sum(
                account.position is not None
                for account in self.accounts.values()
            ),
            "closed_trades": len(closes),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": len(wins) / len(closes) * 100 if closes else 0.0,
            "profit_factor": (
                gross_profit / gross_loss
                if gross_loss
                else (float("inf") if gross_profit else 0.0)
            ),
        }
