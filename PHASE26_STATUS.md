# Phase 26 — Durable order state & reconciliation

Status: started on `phase-26-durable-reconciliation`, based on green Phase 25.

## Goal
Make future live-order state restart-safe and reconciliation-first before any real exchange adapter is introduced.

## Implemented
- atomic durable order ledger;
- idempotent client-order identity across process restarts;
- persisted exchange-order identity and lifecycle state;
- corrupted ledger fails closed;
- durable ledger regression tests.

## Next
- exchange-state reconciliation contract;
- explicit UNKNOWN recovery flow;
- stale-order detection;
- durable audit events;
- pre-submit safety-decision freshness;
- CI integration with Phase 21–25 safety suites.

## Safety boundary
No exchange connector, credentials, or live order endpoint is present. Phase 26 cannot place live orders.
