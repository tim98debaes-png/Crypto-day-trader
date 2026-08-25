# Phase 18 — Candidate registry and controlled rollback

Status: implemented

Phase 18 adds a persistent, auditable registry for optimizer candidates. It records candidate versions, promotion decisions, the active candidate and rollback events.

Safety properties:
- Deterministic candidate IDs are derived from candidate content.
- Promotion reuses the Phase 17 quality gates and still requires explicit human approval.
- Only one candidate can be active at a time.
- Promoting a new candidate marks the previous active candidate as rolled back.
- Rollback can explicitly restore a known candidate or deactivate the current candidate.
- Registry writes are atomic.
- The registry never places orders.

Next: connect the registry to the Streamlit optimizer dashboard and paper session with visible active-version state and manual rollback.
