# Phase 20 — Active candidate paper-trading gate

Status: in progress; registry-backed execution and Streamlit dashboard integration implemented.

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
- Streamlit Candidate Registry page wired to the view model;
- read-only UI (no promotion/rollback actions);
- CI compile and regression coverage for execution, dashboard view and UI wiring.

Safety:
- CandidateRegistry remains the source of truth;
- dashboard view and UI are read-only;
- selection never promotes or rolls back candidates;
- selection never places live orders;
- missing/mismatched candidates fail closed for new entries;
- stale optimizer session state cannot bypass the registry at the execution boundary.

Next: verify the full Phase 20 CI result and then close/merge the integration PR. After that, Phase 21 can focus on paper-session monitoring and automatic rollback triggers, still without live execution.
