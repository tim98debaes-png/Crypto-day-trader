"""Multi-asset paper portfolio aggregation.

Simulation only. The configured capital is shared across selected symbols.
Paper state can be persisted atomically while running inside Streamlit so a
process restart can resume the same paper session.
"""

from dataclasses import dataclass, field
from typing import Optional

from paper_engine import PaperAccount, PaperPosition
from paper_state import default_path, load, save


def _streamlit_context_active() -> bool:
    """Return True only when constructed from an active Streamlit run."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False


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
    persist: Optional[bool] = None
    state_path: Optional[str] = None

    def __post_init__(self):
        if self.total_capital is not None:
            self.capital = float(self.total_capital)
        self.capital = float(self.capital)
        if self.capital <= 0:
            raise ValueError("capital must be positive")
        self.coins = [str(symbol).upper() for symbol in self.coins]
        if self.persist is None:
            self.persist = _streamlit_context_active()
        self._config = {
            "capital": self.capital,
            "risk_pct": float(self.risk_pct),
            "fee_pct": float(self.fee_pct),
            "slippage_pct": float(self.slippage_pct),
            "max_daily_loss_pct": float(self.max_daily_loss_pct),
            "coins": list(self.coins),
        }
        self.state_path = self.state_path or str(default_path(self._config))
        self.peak_equity = self.capital
        if not self.equity_history:
            self.equity_history.append(self.capital)
        if self.persist:
            self._restore_state()

    def _allocation(self) -> float:
        count = len(self.coins)
        if count <= 0:
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
            self._save_state()
        return self.accounts[symbol]

    @staticmethod
    def _account_to_dict(account: PaperAccount) -> dict:
        position = account.position
        return {
            "capital": account.capital,
            "cash": account.cash,
            "risk_pct": account.risk_pct,
            "fee_pct": account.fee_pct,
            "slippage_pct": account.slippage_pct,
            "max_daily_loss_pct": account.max_daily_loss_pct,
            "day_start_equity": account.day_start_equity,
            "current_day": account.current_day,
            "audit_log": list(account.audit_log[-10000:]),
            "position": None if position is None else {
                "symbol": position.symbol,
                "direction": position.direction,
                "entry_price": position.entry_price,
                "quantity": position.quantity,
                "stop_price": position.stop_price,
                "target_price": position.target_price,
                "opened_at": position.opened_at,
                "entry_fee": position.entry_fee,
            },
        }

    @staticmethod
    def _account_from_dict(data: dict) -> PaperAccount:
        account = PaperAccount(
            capital=float(data["capital"]),
            cash=float(data["cash"]),
            risk_pct=float(data["risk_pct"]),
            fee_pct=float(data["fee_pct"]),
            slippage_pct=float(data["slippage_pct"]),
            max_daily_loss_pct=float(data["max_daily_loss_pct"]),
            day_start_equity=data.get("day_start_equity"),
            current_day=data.get("current_day"),
            audit_log=list(data.get("audit_log", [])),
        )
        position = data.get("position")
        if isinstance(position, dict):
            account.position = PaperPosition(
                symbol=str(position["symbol"]),
                direction=str(position["direction"]),
                entry_price=float(position["entry_price"]),
                quantity=float(position["quantity"]),
                stop_price=float(position["stop_price"]),
                target_price=float(position["target_price"]),
                opened_at=str(position["opened_at"]),
                entry_fee=float(position.get("entry_fee", 0.0)),
            )
        return account

    def _state_dict(self) -> dict:
        return {
            "accounts": {
                symbol: self._account_to_dict(account)
                for symbol, account in self.accounts.items()
            },
            "coins": list(self.coins),
            "equity_history": list(self.equity_history[-10000:]),
            "peak_equity": self.peak_equity,
            "max_drawdown_pct": self.max_drawdown_pct,
        }

    def _restore_state(self) -> bool:
        state = load(self.state_path, self._config)
        if not state:
            return False
        try:
            restored_accounts = state.get("accounts", {})
            self.accounts = {
                str(symbol).upper(): self._account_from_dict(data)
                for symbol, data in restored_accounts.items()
                if isinstance(data, dict)
            }
            self.equity_history = [
                float(value) for value in state.get("equity_history", [self.capital])
            ] or [self.capital]
            self.peak_equity = float(state.get("peak_equity", self.capital))
            self.max_drawdown_pct = float(state.get("max_drawdown_pct", 0.0))
            return True
        except (KeyError, TypeError, ValueError):
            self.accounts = {}
            self.equity_history = [self.capital]
            self.peak_equity = self.capital
            self.max_drawdown_pct = 0.0
            return False

    def _save_state(self) -> None:
        if not self.persist:
            return
        try:
            save(self.state_path, self._config, self._state_dict())
        except OSError:
            # Paper trading must remain usable if local persistence is unavailable.
            pass

    def save_state(self) -> None:
        """Explicitly persist the current paper portfolio."""
        self._save_state()

    def _record_equity(self, value: float) -> None:
        value = float(value)
        self.equity_history.append(value)
        self.equity_history = self.equity_history[-10000:]
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
        long_trades = [event for event in closes if str(event.get("direction", "")).upper() == "LONG"]
        short_trades = [event for event in closes if str(event.get("direction", "")).upper() == "SHORT"]
        gross_profit = sum(float(event.get("pnl", 0)) for event in wins)
        gross_loss = abs(sum(float(event.get("pnl", 0)) for event in losses))
        total_fees = sum(
            float(event.get("entry_fee", 0)) + float(event.get("exit_fee", 0))
            for event in closes
        )
        return_pct = round((current_equity / self.capital - 1.0) * 100.0, 10)
        current_drawdown_pct = round(
            (self.peak_equity - current_equity) / self.peak_equity * 100.0,
            10,
        ) if self.peak_equity > 0 else 0.0
        avg_trade = (
            sum(float(event.get("pnl", 0)) for event in closes) / len(closes)
            if closes else 0.0
        )
        best_trade = max((float(event.get("pnl", 0)) for event in closes), default=0.0)
        worst_trade = min((float(event.get("pnl", 0)) for event in closes), default=0.0)
        win_rate_pct = len(wins) / len(closes) * 100 if closes else 0.0
        profit_factor = (
            gross_profit / gross_loss
            if gross_loss
            else (float("inf") if gross_profit else 0.0)
        )
        payoff_ratio = gross_profit / len(wins) / (gross_loss / len(losses)) if wins and losses else 0.0
        result = {
            "equity": current_equity,
            "return_pct": return_pct,
            "peak_equity": self.peak_equity,
            "current_drawdown_pct": current_drawdown_pct,
            "max_drawdown_pct": round(self.max_drawdown_pct, 10),
            "symbols": len(self.accounts),
            "open_positions": sum(account.position is not None for account in self.accounts.values()),
            "closed_trades": len(closes),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(win_rate_pct, 10),
            "profit_factor": round(profit_factor, 10) if profit_factor != float("inf") else profit_factor,
            "avg_trade": avg_trade,
            "expectancy": avg_trade,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "total_fees": total_fees,
            "payoff_ratio": round(payoff_ratio, 10),
            "long_trades": len(long_trades),
            "short_trades": len(short_trades),
        }
        self._save_state()
        return result

    @staticmethod
    def _candidate_approved(candidate: dict) -> bool:
        return str(candidate.get("Status", "")).upper() == "ROBUST"

    def process(self, symbol: str, candidate: dict, market: dict, scores: dict) -> dict:
        symbol = str(symbol).upper()
        account = self.account(symbol)
        price = float(market["price"])
        timestamp = market.get("timestamp")
        if price <= 0:
            raise ValueError("market price must be positive")

        if account.position is not None:
            position = account.position
            if position.direction == "LONG":
                if price <= position.stop_price:
                    pnl = account.close_position(price, "SL", timestamp)
                    self._save_state()
                    return {"action": "CLOSE", "reason": "SL", "pnl": pnl}
                if price >= position.target_price:
                    pnl = account.close_position(price, "TP", timestamp)
                    self._save_state()
                    return {"action": "CLOSE", "reason": "TP", "pnl": pnl}
                if float(scores.get("long_score", 0)) <= 0:
                    pnl = account.close_position(price, "SIGNAL", timestamp)
                    self._save_state()
                    return {"action": "CLOSE", "reason": "SIGNAL", "pnl": pnl}
            else:
                if price >= position.stop_price:
                    pnl = account.close_position(price, "SL", timestamp)
                    self._save_state()
                    return {"action": "CLOSE", "reason": "SL", "pnl": pnl}
                if price <= position.target_price:
                    pnl = account.close_position(price, "TP", timestamp)
                    self._save_state()
                    return {"action": "CLOSE", "reason": "TP", "pnl": pnl}
                if float(scores.get("short_score", 0)) <= 0:
                    pnl = account.close_position(price, "SIGNAL", timestamp)
                    self._save_state()
                    return {"action": "CLOSE", "reason": "SIGNAL", "pnl": pnl}
            return {"action": "HOLD", "position": position.direction}

        if not self._candidate_approved(candidate):
            return {"action": "SKIP", "reason": "candidate_not_robust"}

        long_score = float(scores.get("long_score", 0))
        short_score = float(scores.get("short_score", 0))
        direction = (
            "LONG" if long_score > short_score and long_score > 0
            else "SHORT" if short_score > long_score and short_score > 0
            else None
        )
        if direction is None:
            return {"action": "SKIP", "reason": "no_direction"}

        params = candidate.get("Strategy Params") or {}
        stop_distance = float(scores.get("stop_distance", params.get("sl_atr", 0)))
        rr = float(scores.get("rr", params.get("rr", 0)))
        if stop_distance <= 0 or rr <= 0:
            return {"action": "SKIP", "reason": "invalid_risk_parameters"}

        position = account.open_position(symbol, direction, price, stop_distance, rr, timestamp)
        self._save_state()
        return {"action": "OPEN", "direction": direction, "position": position}

    def rows(self) -> list[dict]:
        rows = []
        for symbol, account in self.accounts.items():
            position = account.position
            rows.append({
                "Symbol": symbol,
                "Position": "FLAT" if position is None else f"{position.direction} @ {position.entry_price:.8f}",
                "Cash": round(account.cash, 8),
                "Equity": round(account.equity(), 8),
                "Closed Trades": sum(1 for event in account.audit_log if event.get("event") == "CLOSE"),
            })
        return rows

    def totals(self) -> dict:
        return self.summary()
