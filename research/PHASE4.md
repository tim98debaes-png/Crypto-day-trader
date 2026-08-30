# Phase 4 — trade-level diagnosis

Purpose: explain the Phase 3 A/B/C benchmark before changing strategy parameters.

Outputs per strategy:
- `trades.json`: every audit event from the backtester
- `equity_curve.json`: equity trajectory
- `diagnosis.json`: attribution by symbol, direction, exit reason and strategy tier
- `phase4_report.json`: combined machine-readable report

No execution or strategy logic is changed by the diagnostic layer.

A strategy improvement is only considered after the baseline diagnosis is reproducible and the resulting candidate is evaluated out-of-sample.
