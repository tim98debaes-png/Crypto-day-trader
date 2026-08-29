"""Portfolio execution layer for Step 2b research.

This adapter converts normalized strategy signals into the existing
MultiPositionBacktester contract. It keeps strategy decisions separate from
cash/risk/fee/slippage handling.
"""
from __future__ import annotations
from multi_position_backtest import MultiPositionBacktester, MultiPositionBacktestResult


def run_portfolio(candles, signal_provider, *, capital=1000.0, risk_pct=0.5,
                  fee_pct=0.1, slippage_pct=0.02, max_daily_loss_pct=3.0) -> MultiPositionBacktestResult:
    engine=MultiPositionBacktester(capital=capital,risk_pct=risk_pct,fee_pct=fee_pct,slippage_pct=slippage_pct,max_daily_loss_pct=max_daily_loss_pct)
    return engine.run(candles,signal_provider)
