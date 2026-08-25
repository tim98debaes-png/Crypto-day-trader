# Phase 20 — Active candidate paper-trading gate

Status: in progress.

Implemented slice:
- registry-backed read-only active candidate source;
- paper-trading eligibility rechecked at selection time;
- explicit symbol mismatch protection;
- no-active-candidate fail-closed behavior;
- registry-backed paper execution router seam for the Phase 5 dashboard;
- registry candidate ID attached to the paper execution payload for traceability;
- regression tests for approval, mismatch, stale/weak active state, read-only behavior and router behavior;
- dedicated CI with Python compilation and registry/dashboard regression tests.

Safety:
- CandidateRegistry remains the source of truth;
- selection never promotes or rolls back candidates;
- selection never places live orders;
- a candidate must still satisfy the existing paper quality gate before it can be selected;
- a missing or mismatched active candidate fails closed for new entries.

Next slice: replace the Phase 5 dashboard's direct `active_results` candidate lookup with `on_registry_market()` so executable paper entries are sourced exclusively from the active registry candidate.
