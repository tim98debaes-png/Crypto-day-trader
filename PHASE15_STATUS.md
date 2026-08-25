# Phase 15 — Strategy optimization

Adds a deterministic grid-search optimizer on top of the Phase 14 historical backtester.

Included:
- bounded parameter-grid search;
- risk-aware ranking using return, profit factor and drawdown;
- deterministic result ordering;
- walk-forward train/test evaluation;
- regression tests.

The optimizer does not invent or alter trading logic. A strategy factory supplies the strategy for each parameter set, and every candidate is evaluated through the existing historical paper backtester.

Live exchange execution remains disabled.
