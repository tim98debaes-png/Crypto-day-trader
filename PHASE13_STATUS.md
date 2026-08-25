# Phase 13 — Long-run paper runtime

## Goal
Make the simulation-only paper runtime safer for unattended, long-running tests.

## Implemented
- Runtime supervisor with explicit checkpoints.
- Tick counter and UTC start/last-tick timestamps.
- Configurable checkpoint interval.
- Recovery from transient tick failures.
- Automatic stop after a configurable consecutive-error threshold.
- Checkpoint callback so the application can persist runtime health alongside paper state.
- Deterministic tests for checkpoints, recovery, failure escalation and timestamps.

## Safety
The runtime supervisor only wraps the existing paper tick function. It does not create exchange orders, credentials, or live execution paths.

## Next
Integrate runtime checkpoints with the existing persistent session/portfolio state and surface runtime health in the operations dashboard.
