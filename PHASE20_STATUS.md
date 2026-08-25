# Phase 20 — Active candidate paper-trading gate

Status: integration complete for the paper execution boundary; dashboard cleanup remains optional.

Implemented:
- registry-backed read-only active candidate source;
- paper-trading eligibility rechecked at selection time;
- explicit symbol mismatch protection;
- no-active-candidate fail-closed behavior;
- registry-backed paper execution router seam;
- `PaperExecutionLoop` now treats `CandidateRegistry` as authoritative for new entries;
- the legacy optimizer/session `candidate` argument is retained only for API compatibility and cannot authorize a new entry;
- registry candidate ID returned on paper opens for traceability;
- candidate direction is checked against the registry candidate before opening;
- exits/position management remain available even when no active candidate exists;
- regression tests for approval, mismatch, stale/weak active state, read-only behavior, router behavior and conflicting session candidates;
- dedicated CI with Python compilation and registry/dashboard regression tests.

Safety:
- CandidateRegistry remains the source of truth;
- selection never promotes or rolls back candidates;
- selection never places live orders;
- a candidate must still satisfy the existing paper quality gate before it can be selected;
- a missing or mismatched active candidate fails closed for new entries;
- stale optimizer session state cannot bypass the registry at the execution boundary.

The Phase 5 dashboard can still calculate its signal preview from optimizer/session state for display, but that preview is no longer an authorization source for paper execution. The next cleanup can make the dashboard preview itself registry-backed as well.
