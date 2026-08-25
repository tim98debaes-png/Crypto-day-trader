# Phase 16 — Optimizer dashboard integration

Phase 15's deterministic optimizer is now exposed through the Streamlit application.

Included:
- historical candle CSV upload;
- parameter search for signal threshold and RR;
- ranked optimization results;
- 70/30 walk-forward validation;
- explicit out-of-sample metrics;
- regression coverage and dedicated CI.

Safety boundary:
- optimization uses historical data only;
- the dashboard does not place live orders;
- candidates are not automatically promoted to the paper/live router.

Next phase can add controlled candidate promotion and stronger validation gates without coupling optimization to live execution.
