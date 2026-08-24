"""Multi-asset paper portfolio aggregation.

Simulation only. This module never places exchange orders.
"""

from dataclasses import dataclass, field
from typing import Optional

from paper_engine import PaperAccount


@dataclass
class PaperPortfolio:
    capital: float = 1000.0
    risk_pct: float = 0.5
    fee_pct: float = 0.1
    slippage_pct: float = 0.02
    max_daily_loss_pct: float = 3.0
    accounts: dict[str, PaperAccount] = field(default_factory=dict)

    def account(self, symbol: str) -> PaperAccount:
        symbol = symbol.upper()
        if symbol not in self.accounts:
            self.accounts[symbol] = PaperAccount(
                capital=self.capital,
                cash=self.capital,
                risk_pct=self.risk_pct,
                fee_pct=self.fee_pct,
                slippage_pct=self.slippage_pct,
                max_daily_loss_pct=self.max_daily_loss_pct,
            )
        return self.accounts[symbol]

    def equity(self, marks: Optional[dict] = None) -> float:
        marks = marks or {}
        return float(sum(account.equity(marks.get(symbol)) for symbol, account in self.accounts.items()))

    def audit_log(self) -> list:
        events = []
        for symbol, account in self.accounts.items():
            for event in account.audit_log:
                item = dict(event)
                item.setdefault("symbol", symbol)
                events.append(item)
        return sorted(events, key=lambda item: str(item.get("timestamp", "")))

    def summary(self, marks: Optional[dict] = None) -> dict:
        events = self.audit_log()
        closes = [event for event in events if event.get("event") == "CLOSE"]
        wins = [event for event in closes if float(event.get("pnl", 0)) > 0]
        losses = [event for event in closes if float(event.get("pnl", 0)) < 0]
        gross_profit = sum(float(event.get("pnl", 0)) for event in wins)
        gross_loss = abs(sum(float(event.get("pnl", 0)) for event in losses))
        return {
            "equity": self.equity(marks),
            "symbols": len(self.accounts),
            "open_positions": sum(account.position is not None for account in self.accounts.values()),
            "closed_trades": len(closes),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": len(wins) / len(closes) * 100 if closes else 0.0,
            "profit_factor": gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0),
        }
