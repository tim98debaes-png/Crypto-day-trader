# Phase 18 — Candidate registry and controlled rollback

Status: implemented

Phase 18 adds a persistent, auditable registry for optimizer candidates. It records candidate versions, promotion decisions, the active candidate and rollback events.

Safety properties:
- Candidates are deterministic IDs derived from their content.
- Promotion reuses the Phase 17 quality gates and still requires explicit human approval.
- Only one candidate can be active at a time.
- Promoting a new candidate marks the previous active candidate as rolled back.
- Rollback can explicitly restore a known candidate or deactivate the current candidate.
- State is written atomically to avoid partially written registry files.
- No live orders are placed by the registry.

Next: connect the registry to the Streamlit optimizer dashboard and paper session, with visible active-version state and a manual rollback control.
