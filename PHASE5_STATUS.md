# Phase 5 status

## Paper trading engine

Phase 5 provides the execution-simulation layer without enabling live exchange orders.

Implemented:
- deterministic LONG/SHORT paper positions;
- risk-based quantity sizing;
- configurable fees and slippage;
- ATR/strategy-derived stop distance and RR target support;
- daily loss guard;
- position state and equity snapshots;
- open/close audit log;
- optimizer-to-paper candidate gate using the real optimizer OOS/MC output schema;
- strategy signal routing into the paper execution loop;
- regression tests and CI workflow.

The paper gate requires TRADE status, positive OOS return and profit factor, sufficient OOS trades, bounded OOS drawdown, and the Phase 4 robustness/probability thresholds. Legacy normalized test fields remain supported.

Live exchange order placement remains disabled.

## Phase 5 completion gate

Phase 5 is considered complete when the dedicated workflow is green for paper-engine, router, execution, market-feed, signal, strategy-runner, Phase 4 robustness, and Phase 3 regression tests.
