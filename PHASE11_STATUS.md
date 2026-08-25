# Phase 11 — Persistent paper-session lifecycle

## Goal
Persist the operator lifecycle state of the simulation-only live paper session across process restarts.

## Included
- Atomic JSON persistence for RUNNING / PAUSED / STOPPED state.
- Configuration fingerprinting so a different symbol universe or interval cannot restore the wrong session.
- Explicit opt-in persistence on `LivePaperSession` via `persist_state=True`.
- Pause/Resume/Stop transitions are persisted immediately.
- A deliberately stopped or paused paper session stays stopped/paused after a restart.
- No exchange credentials or live order routing are introduced.
- Dedicated Phase 11 regression tests and CI coverage.

## Safety
This remains paper trading only. `LivePaperSession` still consumes public market data and routes decisions into the paper engine; no real exchange orders are enabled.
