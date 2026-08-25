# Phase 19 — Candidate registry dashboard integration

Status: implementation complete for the current integration slice.

Implemented:
- Streamlit registry page under `pages/2_Registry.py`.
- Imports ROBUST/TRADE candidates from `optimizer_results_v850.json` into the persistent registry.
- Shows active candidate ID, strategy, coin and OOS PF.
- Shows deterministic candidate table and recent audit events.
- Manual promotion requires an explicit human approval button.
- Manual rollback can deactivate the active candidate or restore a prior rolled-back candidate.
- No live orders are introduced.
- CI validates the existing registry/dashboard regression tests and Python compilation of the new Streamlit page and registry modules.

Validation:
- Existing Phase 19 dashboard test run: success.
- Latest Phase 18 CI on the Phase 19 branch: success.

Next: integrate the registry state directly into the main optimizer/paper-trading view so the active candidate/version is visible without navigating to a separate page, while preserving explicit promotion/rollback controls.
