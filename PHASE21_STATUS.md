# Phase 21 — Paper-session monitoring & rollback

Status: STARTED — implementation not yet complete.

## Current state
- Phase 20 is complete and green.
- CandidateRegistry remains authoritative for paper-trading candidate selection.
- Phase 21 working branches exist; the primary working branch is `phase-21-monitoring-rollback`.
- No Phase 21 implementation has yet been validated by a dedicated green CI gate.

## Passed
- Phase 20 active-candidate CI gate: SUCCESS.
- Phase 19 registry-dashboard CI gate: SUCCESS.
- Phase 20 registry/dashboard regression coverage is green.

## Open
- Build the paper-session monitoring layer.
- Define and test fail-closed breach detection for equity/P&L, drawdown and daily-loss limits.
- Connect qualifying breaches to explicit registry rollback/deactivation without enabling live execution.
- Add Phase 21 regression tests and CI.

## Next step
Implement the read-only paper-session monitor and rollback decision engine first, with deterministic tests for normal operation, threshold breaches, stale/missing candidate state and no-active-candidate behavior. Then add the dedicated Phase 21 CI gate.

## Safety
Phase 21 remains paper-only. Monitoring may recommend or trigger registry state changes only through explicit, auditable rollback paths; it must never place live exchange orders.
