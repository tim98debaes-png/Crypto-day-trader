# Phase 23 — Sustained paper reliability

Status: implementation in progress on `phase-23-paper-validation`.

## Scope
Phase 23 proves that the complete paper-trading chain remains deterministic and recoverable during long sessions and process restarts.

## Implemented
- deterministic bounded reliability harness;
- long-run market-event replay without exchange access;
- persistent observability checkpoint recovery;
- restart/recovery validation;
- checkpoint integrity and stale-session regression tests;
- capital/equity invariants;
- dedicated Phase 23 CI gate;
- reuse of Phase 21/22 safety regression suites.

## Safety boundary
- paper-only;
- no exchange order API;
- no live credentials;
- reliability harness cannot authorize entries;
- observability remains read-only with respect to trading authorization;
- failures are reported as violations rather than silently accepted.

## Exit criteria
1. Phase 23 CI is green.
2. Long-run replay passes with zero reliability violations.
3. Restart recovery preserves checkpoint sequence and active-candidate identity.
4. Corrupt state fails closed.
5. Stale sessions are detected.
6. Phase 21/22 safety suites remain green.
7. A sustained paper-validation period is completed before any live-execution design is enabled.

Phase 23 is not complete until all exit criteria are evidenced.
