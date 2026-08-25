# Phase 25 — Controlled Live Execution Architecture

Status: started on `phase-25-controlled-live-architecture`, based on green Phase 24.

## Scope
Build the smallest possible live-execution boundary without connecting to an exchange or introducing live credentials.

Implemented:
- transport-neutral `LiveOrderRequest` contract;
- explicit order side/type and validation;
- `ControlledLiveExecutor` safety wrapper;
- safety decision must be LIVE + `LIVE_AUTHORIZED` immediately before transport submission;
- paper or blocked decisions never call the transport;
- invalid requests never call the transport;
- recording fake transport tests prove the boundary.

## Safety boundary
- no exchange SDK;
- no exchange endpoint;
- no API keys or secrets;
- no live transport implementation;
- no automatic live activation;
- Phase 24 remains the authorization source of truth.

## Next
Add idempotency, pre-submit revalidation, order lifecycle/audit contracts, timeout/reconciliation behavior, and a comprehensive negative-test suite before any real exchange adapter is considered.

Phase 25 is not permission to trade live.
