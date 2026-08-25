# Phase 20 — Active candidate paper-trading gate

Status: in progress; registry-backed execution and dashboard view model implemented.

Implemented:
- registry-backed read-only active candidate source;
- paper-trading eligibility rechecked at selection time;
- explicit symbol mismatch protection;
- no-active-candidate fail-closed behavior;
- registry-backed paper execution router seam;
- `PaperExecutionLoop` treats `CandidateRegistry` as authoritative for new entries;
- legacy optimizer/session candidate cannot authorize a new entry;
- registry candidate ID returned on paper opens;
- candidate direction checked against the registry candidate;
- registry-backed dashboard view model for active candidate and candidate rows;
- dedicated tests for the dashboard view model;
- CI compilation and regression coverage updated.

Safety:
- CandidateRegistry remains the source of truth;
- dashboard view is read-only;
- no promotion/rollback side effects from the view model;
- selection never places live orders;
- missing/mismatched candidates fail closed for new entries;
- stale optimizer session state cannot bypass the registry at the execution boundary.

Next slice: wire `build_candidate_dashboard()` and `build_candidate_rows()` into the actual Streamlit UI once the application's UI entry point is identified on the integration branch.
