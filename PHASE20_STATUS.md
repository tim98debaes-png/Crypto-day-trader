# Phase 20 — Active candidate paper-trading gate

Status: in progress.

Implemented slice:
- registry-backed read-only active candidate source;
- paper-trading eligibility rechecked at selection time;
- explicit symbol mismatch protection;
- no-active-candidate fail-closed behavior;
- regression tests for approval, mismatch, stale/weak active state and read-only behavior;
- dedicated CI with Python compilation and registry/dashboard regression tests.

Safety:
- CandidateRegistry remains the source of truth;
- this module never promotes or rolls back candidates;
- this module never places orders;
- a candidate must still satisfy the existing paper quality gate before it can be selected.

Next slice: wire `get_active_candidate()` into the existing Phase 5 paper-trading dashboard so the dashboard stops sourcing executable candidates directly from optimizer session state.
