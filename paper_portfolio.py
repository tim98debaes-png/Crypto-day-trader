"""Multi-asset paper portfolio used by the Streamlit paper session."""

from datetime import datetime, timezone

from paper_engine import PaperAccount
from paper_execution import PaperExecutionLoop
from paper_strategy_runner import PaperStrategyRunner


class PaperPortfolio:
    def __init__(self, total_capital=1000.0, coins=None):
        self.total_capital = float(total_capital)
        self.coins = list(coins or [])
        allocation = self.total_capital / max(len(self.coins), 1)
        self.loops = {
            coin: PaperExecutionLoop(
                PaperAccount(capital=allocation)
            )
            for coin in self.coins
        }
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.running = False

    def process(self, coin, candidate, market, indicators):
        if coin not in self.loops:
            allocation = self.total_capital / max(len(self.coins) + 1, 1)
            self.loops[coin] = PaperExecutionLoop(
                PaperAccount(capital=allocation)
            )
            self.coins.append(coin)

        return PaperStrategyRunner(self.loops[coin]).process(
            market,
            candidate,
            indicators,
        )

    def rows(self):
        rows = []
        for coin, loop in self.loops.items():
            summary = loop.summary()
            position = loop.account.position
            rows.append({
                "Coin": coin,
                "Equity": round(summary["equity"], 2),
                "Trades": summary["closed_trades"],
                "Winrate %": round(summary["win_rate_pct"], 1),
                "Profit factor": round(summary["profit_factor"], 2),
                "Max DD %": round(summary["max_drawdown_pct"], 2),
                "Position": (
                    f"{position.direction} @ {position.entry_price:.6g}"
                    if position else "FLAT"
                ),
            })
        return rows

    def trade_log(self):
        events = []
        for coin, loop in self.loops.items():
            for event in loop.account.audit_log:
                item = dict(event)
                item["coin"] = coin
                events.append(item)
        return sorted(events, key=lambda item: item.get("timestamp", ""))

    def totals(self):
        equity = sum(loop.account.equity() for loop in self.loops.values())
        closed = sum(loop.stats.closed_trades for loop in self.loops.values())
        wins = sum(loop.stats.wins for loop in self.loops.values())
        gross_profit = sum(loop.stats.gross_profit for loop in self.loops.values())
        gross_loss = sum(loop.stats.gross_loss for loop in self.loops.values())
        return {
            "equity": equity,
            "return_pct": (equity / self.total_capital - 1) * 100,
            "closed_trades": closed,
            "win_rate_pct": wins / closed * 100 if closed else 0.0,
            "profit_factor": gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0),
        }
