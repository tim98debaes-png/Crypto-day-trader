# Phase 19 — Registry dashboard integration

Status: in progress.

Implemented first slice:
- dashboard-facing adapter for the Phase 18 candidate registry;
- deterministic candidate table data for Streamlit;
- visible active candidate snapshot;
- explicit rollback action returning an audit event;
- regression tests;
- dedicated CI workflow.

Safety:
- registry remains the source of truth;
- rollback is explicit and auditable;
- no live order execution is introduced.

Next slice: wire the adapter into the existing Streamlit optimizer/paper dashboard and expose the active candidate/version plus manual rollback control.
