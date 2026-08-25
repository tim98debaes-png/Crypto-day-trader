# Phase 28 — Exchange Adapter Sandbox & Contract Testing

Status: implementation complete; CI validation required.

## Implemented
- deterministic exchange sandbox with no external endpoint;
- ACK, REJECT, TIMEOUT and RATE_LIMIT scenarios;
- deterministic partial-fill simulation;
- integration with controlled order lifecycle;
- timeout -> UNKNOWN -> reconciliation-required behavior;
- duplicate submission protection;
- regression suite covering Phase 21–28;
- dedicated Phase 28 CI workflow.

## Safety boundary
The sandbox is local/test-only. No exchange SDK, URL, credentials, API key, websocket, or real order endpoint is present.

## Exit criteria
1. Sandbox scenarios pass.
2. Lifecycle integration passes.
3. Partial fills are deterministic.
4. Reject/rate-limit behavior is fail-safe.
5. Timeout requires reconciliation.
6. Duplicate orders never resubmit.
7. Phase 21–27 regressions remain green.
8. No live connectivity is introduced.

Phase 28 is complete only after CI is green.
