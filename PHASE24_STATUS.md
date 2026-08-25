# Phase 24 — Pre-live safety gate

Status: started on `phase-24-prelive-safety`, based on the green Phase 23 paper-validation branch.

## Goal
Build and verify the final safety boundary before any future live-execution implementation is considered.

## Scope
- explicit live-mode disabled-by-default configuration;
- fail-closed execution authorization;
- environment/account separation checks;
- credential presence and mode validation without exposing secrets;
- notional/risk limits and kill-switch contract;
- prevention of paper/live mode ambiguity;
- audit events for authorization decisions;
- CI tests proving no live order path is reachable while live mode is disabled.

## Non-goals
- no live orders in Phase 24;
- no real exchange credentials;
- no automatic activation of live trading;
- no bypass of candidate validation, monitoring, rollback, or risk controls.

## Exit criteria
1. Safety gate has explicit, deterministic authorization states.
2. Default configuration remains paper-only.
3. Missing/ambiguous live configuration fails closed.
4. Risk/kill-switch violations block authorization.
5. Paper mode cannot accidentally route to a live adapter.
6. All authorization decisions are auditable without secrets.
7. CI proves the boundary with positive and negative tests.
8. Phase 23 regression suite remains green.

Phase 24 is not permission to trade live; it is the construction and verification of the safety gate that must exist before any later live-execution phase.
