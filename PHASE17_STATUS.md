# Phase 17 — Controlled candidate promotion

Phase 17 adds a safety layer between optimizer output and paper-trading eligibility.

Included:
- deterministic normalization of walk-forward OOS metrics;
- reuse of the existing paper quality gates;
- explicit human approval requirement;
- clear BLOCKED/PROMOTED decision objects;
- regression tests and dedicated CI;
- no live execution or automatic promotion.

Promotion requires:
- positive OOS return;
- OOS profit factor >= 1.20;
- at least 15 OOS trades;
- OOS drawdown better than -20%;
- stability >= 60;
- MC P05 > -10%;
- explicit human approval.

Next phase: paper-session candidate registry and controlled rollout/rollback tracking.
