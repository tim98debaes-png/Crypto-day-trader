# Phase 7 status

## Portfolio performance analytics

Phase 7 expands the paper portfolio summary into a richer performance contract for the dashboard and future reporting integrations.

Implemented:
- normalized return, win-rate and drawdown percentages;
- gross profit and gross loss;
- total entry/exit fees for closed trades;
- expectancy / average trade;
- payoff ratio;
- LONG and SHORT trade counts;
- profit factor with stable floating-point output;
- regression coverage for the detailed metric set.

The paper engine remains simulation-only and live exchange order placement remains disabled.

Next step: expose the expanded metrics in the paper dashboard and add durable reporting/export support without changing execution semantics.
