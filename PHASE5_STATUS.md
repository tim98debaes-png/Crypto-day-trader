# Phase 5 status

## Paper trading engine

Phase 5 starts the execution-simulation layer without enabling live orders.

Implemented:
- deterministic LONG/SHORT paper positions;
- risk-based quantity sizing;
- configurable fees and slippage;
- ATR/strategy-derived stop distance and RR target support;
- daily loss guard;
- position state and equity snapshots;
- open/close audit log;
- regression tests and CI workflow.

Next integration step: connect the validated optimizer output to this paper account so only candidates that pass the Phase 4 robustness gates can generate paper-trading entries.

Live exchange order placement remains disabled.
