# Phase 14 — Historical backtesting

## Included
- Deterministic historical candle runner.
- Reuses `PaperAccount` for fees, slippage, risk sizing, daily-loss protection and audit events.
- LONG and SHORT signals.
- Stop-loss, take-profit and explicit signal-close handling.
- Chronological input validation.
- Equity curve and summary metrics including return, drawdown, win rate and profit factor.
- End-of-test position closure.
- Regression tests.

## Safety
The backtester is simulation-only. It has no exchange credentials and cannot place live orders.
