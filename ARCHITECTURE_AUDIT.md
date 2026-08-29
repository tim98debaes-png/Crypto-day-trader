# Architecture audit and benchmark plan

## Executive conclusion

The current project is stronger as a paper-trading/risk-control prototype than as a statistically validated trading strategy. The main architectural weakness is that strategy research, backtesting, paper execution and production-style orchestration are not yet driven by one identical event model. That makes it too easy for a strategy to pass CI while its research assumptions differ from paper behavior.

## A/B architectures

### A — legacy feature-rich architecture
The historical design used multiple timeframes and a broader feature set: EMA/RSI/MACD, volume, ATR, trend strength and volatility regime. It should be reconstructed as a research candidate, not assumed profitable from a small historical run.

### B — current regime/setup/trigger architecture
The current implementation uses a regime filter, pullback setup and directional trigger. This is conceptually cleaner than a flat 5/5 score, but it currently has too little evidence to justify replacing A.

### Recommended C — modular hybrid
Use a pipeline:
1. Universe/liquidity filter.
2. Market regime filter (BTC/market-wide direction and volatility).
3. Asset regime/trend features.
4. Setup detector (pullback/reversion or breakout).
5. Trigger confirmation.
6. Cross-asset ranking.
7. Portfolio/risk gate.
8. Execution/fill model.
9. Exit state machine.

Every stage returns a typed decision and diagnostics. No stage should silently mutate strategy state.

## Research protocol

For every candidate architecture use the same historical data, universe, fees, slippage and portfolio constraints. Split the data chronologically into train, validation and untouched out-of-sample periods. Optimize only on train, select the architecture on validation, and report OOS once.

Required metrics: net return, profit factor, expectancy in R, win rate, max drawdown, Sharpe/Sortino where sample size permits, turnover, fee drag, slippage drag, exposure, MAE/MFE, trade duration, LONG/SHORT split, asset split, regime split and benchmark return.

Reject a strategy if its edge disappears after realistic fees/slippage, if results are concentrated in a tiny number of trades/assets, or if OOS performance is materially below validation.

## External architecture comparison

### Freqtrade
Freqtrade separates strategy callbacks from a repeated trading loop and provides backtesting, dry-run and hyperoptimization. Its backtest flow explicitly simulates entry/exit callbacks and fees. This is a useful reference for keeping strategy logic independent from execution. citeturn0search7turn0search19

### QuantConnect LEAN
LEAN uses one event-driven engine for research, backtesting and live trading, with separate data-feed, transaction, portfolio and result-processing components. Its streaming model is specifically designed to avoid look-ahead differences between batch backtests and live behavior. This is the strongest architectural reference for our project. citeturn0search1turn0search2

### Jesse
Jesse is particularly relevant for our research problem: it provides candle-by-candle backtesting, detailed trade/equity metrics, benchmark comparisons, Monte Carlo analysis and ML research workflows. Its research API is designed to make backtesting a pure/reproducible function. citeturn1search0turn1search2turn1search6

### Hummingbot
Hummingbot strongly separates strategy logic from exchange connectors and order/account streams. Its connector architecture is useful for our execution layer because exchange-specific networking should not leak into strategy decisions. It also has paper trading and backtesting support. citeturn1search5turn1search13turn1search16

## Code findings

### Critical
1. `HistoricalBacktester` is single-position even though `PaperAccount` supports multiple positions. This makes historical results structurally different from multi-asset paper runs.
2. `HistoricalBacktester` checks stop/target using `close` only. With OHLC data, a candle can hit a stop or target intrabar even when its close does not. This creates execution-model error.
3. The current scanner ranks volatility and momentum using absolute values. That can select extreme moves without distinguishing continuation from exhaustion. Direction and regime should be explicit features.
4. Correlation uses only six returns. That is too short for a stable correlation estimate; it should be treated as a concentration heuristic, not predictive correlation.

### High priority
5. Strategy research needs a single feature snapshot so the old and new architectures can consume identical inputs.
6. Exit logic should be a state machine (initial risk, TP1, trailing, signal invalidation, time stop), not a collection of independent checks.
7. Diagnostics must be part of the typed strategy decision rather than ad-hoc dictionaries.
8. The full release CI must be the only release gate; sub-workflows are insufficient evidence.

### Medium priority
9. The repository contains historical phase/status artifacts from many iterations. They are useful history but should not be treated as current production specifications.
10. Configuration is spread across modules. A single validated runtime configuration should be the source of truth.

## Efficiency target

Do not add more indicators by default. Compute one feature snapshot per symbol/timeframe and reuse it for ranking, entry, risk and diagnostics. Cache indicators by candle timestamp and symbol. This reduces repeated computation and makes A/B testing deterministic.

## Current decision

Freeze live strategy changes until the A/B benchmark is implemented. Do not use 15-minute or 1-hour paper runs as the primary strategy-selection mechanism. Use them only after a candidate passes historical and out-of-sample validation.
