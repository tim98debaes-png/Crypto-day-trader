# Phase 23 — Sustained paper reliability

Status: reliability implementation advanced on `phase-23-paper-validation`; the existing Phase 23 CI was green before this hardening pass, and a fresh CI run is required for these latest changes.

## Implemented
- deterministic bounded reliability harness;
- long-run market-event replay without exchange access;
- persistent observability checkpoint recovery;
- multiple process-restart/recovery points in one run;
- checkpoint sequence continuity checks after every restart;
- active-candidate identity preservation checks across recovery;
- checkpoint completeness invariant (`valid events == checkpoints`);
- malformed market data reported as a reliability violation instead of crashing the harness;
- checkpoint integrity and stale-session regression tests;
- capital/equity invariants;
- dedicated Phase 23 CI gate;
- extended Phase 23 recovery/malformed-input regression suite;
- reuse of Phase 21/22 safety regression suites.

## Safety boundary
- paper-only;
- no exchange order API;
- no live credentials;
- reliability harness cannot authorize entries;
- observability remains read-only with respect to trading authorization;
- failures are reported as violations rather than silently accepted.

## Exit criteria
1. Latest Phase 23 CI is green after the hardening changes.
2. Long-run replay passes with zero reliability violations.
3. Multiple restart recovery preserves checkpoint sequence and active-candidate identity.
4. Corrupt state fails closed.
5. Stale sessions are detected.
6. Malformed input fails as a recorded reliability violation rather than a process crash.
7. Phase 21/22 safety suites remain green.
8. A sustained paper-validation period is completed before any live-execution design is enabled.

Phase 23 is not complete until all exit criteria are evidenced.
