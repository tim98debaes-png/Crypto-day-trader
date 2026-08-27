"""Phase 5 paper-trading portfolio state engine with research risk controls."""
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
from phase34_runtime_guard import evaluate_entry_guard
from strategy_risk_controls import RiskConfig

RESEARCH_RISK_PCT = 0.5
RESEARCH_MAX_DAILY_LOSS_PCT = 3.0
RISK_CONFIG = RiskConfig()

@dataclass
class PaperPosition:
    symbol: str
    direction: str
    entry_price: float
    quantity: float
    stop_price: float
    target_price: float
    opened_at: str
    entry_fee: float = 0.0
    initial_quantity: float = 0.0
    initial_stop_distance: float = 0.0
    risk_amount: float = 0.0
    partial_taken: bool = False
    highest_price: float = 0.0
    lowest_price: float = 0.0

@dataclass
class PaperAccount:
    capital: float = 1000.0
    cash: float = 1000.0
    risk_pct: float = RESEARCH_RISK_PCT
    fee_pct: float = 0.1
    slippage_pct: float = 0.02
    max_daily_loss_pct: float = RESEARCH_MAX_DAILY_LOSS_PCT
    risk_config: RiskConfig = RISK_CONFIG
    positions: dict[str, PaperPosition] = field(default_factory=dict)
    last_prices: dict[str, float] = field(default_factory=dict)
    day_start_equity: Optional[float] = None
    current_day: Optional[str] = None
    audit_log: list = field(default_factory=list)
    loss_streak: int = 0
    cooldown_until: Optional[str] = None

    def __post_init__(self):
        if self.capital <= 0: raise ValueError("capital must be positive")
        if self.cash <= 0: self.cash = self.capital
        if self.risk_pct <= 0: raise ValueError("risk_pct must be positive")
        if self.max_daily_loss_pct <= 0: raise ValueError("max_daily_loss_pct must be positive")
        if self.day_start_equity is None: self.day_start_equity = self.capital
        if self.current_day is None: self.current_day = self._today()

    @property
    def position(self) -> Optional[PaperPosition]: return next(iter(self.positions.values()), None)
    @staticmethod
    def _today() -> str: return datetime.now(timezone.utc).date().isoformat()
    @staticmethod
    def _parse_timestamp(value: Optional[str]) -> datetime:
        if not value: return datetime.now(timezone.utc)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    def _roll_day(self, timestamp: Optional[str] = None) -> None:
        day=(timestamp or datetime.now(timezone.utc).isoformat())[:10]
        if day != self.current_day:
            self.current_day=day; self.day_start_equity=self.equity(); self.loss_streak=0; self.cooldown_until=None
    def has_position(self,symbol:str)->bool: return str(symbol) in self.positions
    def equity(self,mark_price:Optional[float]=None,symbol:Optional[str]=None)->float:
        if mark_price is not None and symbol is not None: self.last_prices[str(symbol)]=float(mark_price)
        unrealized=0.0
        for position in self.positions.values():
            price=self.last_prices.get(position.symbol)
            if price is None: continue
            unrealized += ((price-position.entry_price) if position.direction=="LONG" else (position.entry_price-price))*position.quantity
        return float(self.cash+unrealized)
    def daily_loss_pct(self,mark_price:Optional[float]=None,symbol:Optional[str]=None)->float:
        if self.day_start_equity is None or self.day_start_equity<=0: return 100.0
        return (self.equity(mark_price,symbol)/self.day_start_equity-1.0)*100.0
    def _cooldown_active(self,timestamp:Optional[str])->bool:
        return bool(self.cooldown_until and self._parse_timestamp(timestamp)<self._parse_timestamp(self.cooldown_until))
    def _risk_multiplier(self,timestamp:Optional[str])->float:
        if self._cooldown_active(timestamp) or self.loss_streak>=6: return 0.0
        if self.loss_streak>=4: return 0.50
        return 1.0
    def open_risk_pct(self)->float:
        return (sum(p.risk_amount for p in self.positions.values())/self.capital*100.0) if self.capital>0 else 100.0
    def can_open(self,mark_price:float,symbol:str,timestamp:Optional[str]=None)->bool:
        effective_risk=min(self.risk_pct,self.risk_config.max_risk_pct_per_trade)*self._risk_multiplier(timestamp)
        return (not self.has_position(symbol) and len(self.positions)<self.risk_config.max_open_positions
                and self.open_risk_pct()+effective_risk<=self.risk_config.max_total_open_risk_pct
                and self.daily_loss_pct(mark_price,symbol)>-self.max_daily_loss_pct and self.cash>0 and effective_risk>0)
    def open_position(self,symbol:str,direction:str,price:float,stop_distance:float,rr:float,timestamp:Optional[str]=None,*,strategy_ready:bool=True,heartbeat_age_seconds:float|None=0.0,paper_mode:bool=True)->PaperPosition:
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(); self._roll_day(timestamp); symbol=str(symbol); direction=direction.upper()
        if direction not in {"LONG","SHORT"}: raise ValueError("direction must be LONG or SHORT")
        if price<=0 or stop_distance<=0 or rr<=0: raise ValueError("price, stop_distance and rr must be positive")
        if self.has_position(symbol): raise RuntimeError(f"paper account already has an open position for {symbol}")
        guard=evaluate_entry_guard(paper_mode=paper_mode,strategy_ready=strategy_ready,heartbeat_age_seconds=heartbeat_age_seconds,drawdown_pct=self.daily_loss_pct(price,symbol),max_drawdown_pct=20.0)
        if not guard.allowed: raise RuntimeError("paper account is not allowed to open a position: "+",".join(guard.reasons))
        if not self.can_open(price,symbol,timestamp): raise RuntimeError("paper account is not allowed to open a position")
        effective_risk_pct=min(self.risk_pct,self.risk_config.max_risk_pct_per_trade)*self._risk_multiplier(timestamp); risk_amount=self.cash*effective_risk_pct/100.0; quantity=risk_amount/stop_distance
        entry=price*(1.0+self.slippage_pct/100.0) if direction=="LONG" else price*(1.0-self.slippage_pct/100.0)
        stop=entry-stop_distance if direction=="LONG" else entry+stop_distance; target=entry+stop_distance*rr if direction=="LONG" else entry-stop_distance*rr
        entry_fee=entry*quantity*self.fee_pct/100.0; self.cash-=entry_fee; self.last_prices[symbol]=float(price)
        position=PaperPosition(symbol,direction,entry,quantity,stop,target,timestamp,entry_fee,quantity,stop_distance,risk_amount,False,price,price); self.positions[symbol]=position
        self.audit_log.append({"event":"OPEN","symbol":symbol,"direction":direction,"price":entry,"quantity":quantity,"entry_fee":entry_fee,"risk_amount":risk_amount,"risk_pct":effective_risk_pct,"timestamp":timestamp})
        return position
    def update_trailing_stop(self,symbol:str,price:float,atr_distance:float)->float:
        position=self.positions.get(str(symbol))
        if position is None or atr_distance<=0: return 0.0
        if position.direction=="LONG":
            position.highest_price=max(position.highest_price or price,price); candidate=position.highest_price-self.risk_config.trailing_atr_multiple*atr_distance
            if candidate>position.stop_price and candidate<price: position.stop_price=candidate
        else:
            position.lowest_price=min(position.lowest_price or price,price); candidate=position.lowest_price+self.risk_config.trailing_atr_multiple*atr_distance
            if candidate<position.stop_price and candidate>price: position.stop_price=candidate
        return position.stop_price
    def take_partial_profit(self,symbol:str,price:float,timestamp:Optional[str]=None)->float:
        position=self.positions.get(str(symbol))
        if position is None or position.partial_taken: return 0.0
        quantity=position.quantity*self.risk_config.partial_take_profit_fraction
        if quantity<=0: return 0.0
        timestamp=timestamp or datetime.now(timezone.utc).isoformat()
        if position.direction=="LONG": exit_price=price*(1.0-self.slippage_pct/100.0); gross=(exit_price-position.entry_price)*quantity
        else: exit_price=price*(1.0+self.slippage_pct/100.0); gross=(position.entry_price-exit_price)*quantity
        exit_fee=exit_price*quantity*self.fee_pct/100.0; allocated_entry_fee=position.entry_fee*(quantity/max(position.initial_quantity,quantity))
        pnl=gross-exit_fee-allocated_entry_fee; self.cash+=gross-exit_fee; position.quantity-=quantity; position.entry_fee-=allocated_entry_fee; position.partial_taken=True
        position.stop_price=max(position.stop_price,position.entry_price) if position.direction=="LONG" else min(position.stop_price,position.entry_price)
        self.audit_log.append({"event":"PARTIAL_CLOSE","symbol":symbol,"direction":position.direction,"price":exit_price,"quantity":quantity,"pnl":pnl,"reason":"PARTIAL_TP","timestamp":timestamp})
        return float(pnl)
    def close_position(self,price:float,reason:str="SIGNAL",timestamp:Optional[str]=None,symbol:Optional[str]=None)->float:
        if symbol is None:
            position=self.position
            if position is None: raise RuntimeError("no open paper position")
            symbol=position.symbol
        else:
            symbol=str(symbol); position=self.positions.get(symbol)
            if position is None: raise RuntimeError(f"no open paper position for {symbol}")
        if price<=0: raise ValueError("price must be positive")
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(); self.last_prices[symbol]=float(price)
        if position.direction=="LONG": exit_price=price*(1.0-self.slippage_pct/100.0); gross=(exit_price-position.entry_price)*position.quantity
        else: exit_price=price*(1.0+self.slippage_pct/100.0); gross=(position.entry_price-exit_price)*position.quantity
        exit_fee=exit_price*position.quantity*self.fee_pct/100.0; pnl=gross-position.entry_fee-exit_fee
        self.cash+=gross-exit_fee; del self.positions[symbol]; self.loss_streak=self.loss_streak+1 if pnl<0 else 0
        if self.loss_streak>=8: self.cooldown_until=(self._parse_timestamp(timestamp)+timedelta(minutes=30)).isoformat()
        self.audit_log.append({"event":"CLOSE","symbol":symbol,"direction":position.direction,"price":exit_price,"quantity":position.quantity,"gross_pnl":gross,"entry_fee":position.entry_fee,"exit_fee":exit_fee,"pnl":pnl,"reason":reason,"timestamp":timestamp})
        return float(pnl)
    def position_age_minutes(self,symbol:str,timestamp:Optional[str])->float:
        position=self.positions.get(str(symbol))
        if position is None: return 0.0
        return max(0.0,(self._parse_timestamp(timestamp)-self._parse_timestamp(position.opened_at)).total_seconds()/60.0)
    def snapshot(self,mark_price:Optional[float]=None,symbol:Optional[str]=None)->dict:
        return {"cash":round(self.cash,8),"equity":round(self.equity(mark_price,symbol),8),"daily_loss_pct":round(self.daily_loss_pct(),6),"position_count":len(self.positions),"open_risk_pct":round(self.open_risk_pct(),6),"loss_streak":self.loss_streak,"cooldown_until":self.cooldown_until,"positions":[{"symbol":p.symbol,"direction":p.direction,"entry_price":p.entry_price,"quantity":p.quantity,"stop_price":p.stop_price,"target_price":p.target_price,"partial_taken":p.partial_taken} for p in self.positions.values()],"audit_events":len(self.audit_log)}
