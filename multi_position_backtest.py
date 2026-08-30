"""Multi-position historical backtester using PaperAccount portfolio semantics."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional
from paper_engine import PaperAccount

SignalProvider = Callable[[dict], Optional[dict]]

@dataclass
class BacktestResult:
    initial_capital: float
    final_equity: float
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)

    @property
    def pnl(self):
        return self.final_equity - self.initial_capital

    @property
    def return_pct(self):
        return (self.final_equity / self.initial_capital - 1.0) * 100.0 if self.initial_capital > 0 else 0.0

    @property
    def max_drawdown_pct(self):
        peak = self.initial_capital
        maximum = 0.0
        for row in self.equity_curve:
            equity = float(row['equity'])
            peak = max(peak, equity)
            if peak:
                maximum = max(maximum, (peak - equity) / peak * 100.0)
        return maximum

    def summary(self):
        closes = [e for e in self.trades if e.get('event') == 'CLOSE']
        wins = [e for e in closes if float(e.get('pnl', 0)) > 0]
        losses = [e for e in closes if float(e.get('pnl', 0)) < 0]
        gp = sum(float(e.get('pnl', 0)) for e in wins)
        gl = abs(sum(float(e.get('pnl', 0)) for e in losses))
        return {'initial_capital': self.initial_capital, 'final_equity': self.final_equity, 'pnl': self.pnl,
                'return_pct': round(self.return_pct, 10), 'max_drawdown_pct': round(self.max_drawdown_pct, 10),
                'closed_trades': len(closes), 'wins': len(wins), 'losses': len(losses),
                'win_rate_pct': round(len(wins) / len(closes) * 100, 10) if closes else 0.0,
                'profit_factor': gp/gl if gl else (float('inf') if gp else 0.0)}

class MultiPositionBacktester:
    """Backtest candle-close signals with next-candle-open execution."""
    def __init__(self, capital=1000.0, risk_pct=0.5, fee_pct=0.1, slippage_pct=0.02, max_daily_loss_pct=3.0):
        self.config={'capital':float(capital),'risk_pct':float(risk_pct),'fee_pct':float(fee_pct),'slippage_pct':float(slippage_pct),'max_daily_loss_pct':float(max_daily_loss_pct)}

    @staticmethod
    def _ohlc(row):
        open_price=float(row['open']); close=float(row['close']); high=float(row.get('high',close)); low=float(row.get('low',close))
        if open_price<=0 or high<=0 or low<=0 or low>high or not low<=open_price<=high or not low<=close<=high:
            raise ValueError('invalid candle OHLC: values must be positive and open/close must be inside high/low')
        return open_price, high, low, close

    @staticmethod
    def _exit_trigger(position, open_price, high, low):
        if position.direction=='LONG':
            if open_price <= position.stop_price: return 'SL',open_price
            if open_price >= position.target_price: return 'TP',open_price
            stop_hit,target_hit=low<=position.stop_price, high>=position.target_price
        else:
            if open_price >= position.stop_price: return 'SL',open_price
            if open_price <= position.target_price: return 'TP',open_price
            stop_hit,target_hit=high>=position.stop_price, low<=position.target_price
        if stop_hit: return 'SL',position.stop_price
        if target_hit: return 'TP',position.target_price
        return None

    def _execute_pending(self, account, symbol, open_price, timestamp, pending):
        signal=pending.pop(symbol, None)
        if not signal:
            return
        action=str(signal.get('action','WAIT')).upper()
        if action in {'LONG','SHORT'} and symbol not in account.positions:
            try:
                account.open_position(symbol=symbol,direction=action,price=open_price,stop_distance=float(signal['stop_distance']),rr=float(signal.get('rr',2)),timestamp=timestamp,strategy_score=signal.get('strategy_score'),strategy_tier=signal.get('strategy_tier'))
            except RuntimeError as exc:
                if not str(exc).startswith('paper account is not allowed to open a position'):
                    raise
        elif action=='CLOSE' and symbol in account.positions:
            account.close_position(open_price,'SIGNAL',timestamp,symbol=symbol,trigger_price=open_price)

    def run(self,candles,signal_provider):
        rows=[dict(c) for c in candles]; rows.sort(key=lambda r:str(r.get('timestamp') or r.get('time') or ''))
        account=PaperAccount(**self.config,cash=self.config['capital']); equity_curve=[]; pending_signals={}
        for row in rows:
            timestamp=str(row.get('timestamp') or row.get('time') or '') or None; symbol=str(row.get('symbol','BACKTEST')).upper(); open_price,high,low,close=self._ohlc(row)
            account.last_prices[symbol]=open_price
            self._execute_pending(account,symbol,open_price,timestamp,pending_signals)
            position=account.positions.get(symbol)
            if position:
                event=self._exit_trigger(position,open_price,high,low)
                if event:
                    reason,trigger=event; account.close_position(trigger,reason,timestamp,symbol=symbol,trigger_price=trigger)
            signal=signal_provider(row) or {}; action=str(signal.get('action','WAIT')).upper()
            if action in {'LONG','SHORT','CLOSE'}:
                pending_signals[symbol]=dict(signal)
            account.last_prices[symbol]=close
            equity_curve.append({'timestamp':timestamp or '','equity':round(account.equity(),8),'position_count':len(account.positions),'open_risk_pct':round(account.open_risk_pct(),8)})
        if rows:
            timestamp=str(rows[-1].get('timestamp') or rows[-1].get('time') or '') or None
        return BacktestResult(self.config['capital'],round(account.equity(),8),list(account.audit_log),equity_curve)
