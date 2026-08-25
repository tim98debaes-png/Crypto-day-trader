# Phase 22 — Sustained paper operation and observability

Status: implementation in progress on `phase-22-sustained-paper-observability-v2`.

Implemented in this phase:
- explicit paper-session heartbeats/checkpoints;
- sequence continuity checks so dropped checkpoints are detectable;
- integrity hash on every checkpoint;
- stale-session detection with configurable timeout;
- explicit DEGRADED state when Phase 21 blocks paper entries;
- INVALID state when no valid checkpoint exists;
- safe handling of infinite profit factor in observability output;
- checkpoint retention limit for long-running sessions;
- heartbeat integration into `PaperExecutionLoop` after every market event;
- dedicated Phase 22 CI covering the new observability tests plus the Phase 21 safety boundary.

Safety boundary:
- observability is read-only with respect to trading authorization;
- it never promotes or edits candidates;
- it never bypasses Phase 21 monitoring;
- it never places live orders;
- stale/invalid observability does not authorize a new trade.

Next work before Phase 22 can be marked complete:
- persist/recover the checkpoint stream across process restarts;
- expose session health and checkpoint history in the dashboard;
- add an end-to-end paper-session validation scenario spanning optimizer candidate -> registry -> paper execution -> monitoring -> rollback -> recovery;
- run the final Phase 22 CI gate and only then mark the phase green.
