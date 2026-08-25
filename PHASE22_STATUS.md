# Phase 22 — Sustained paper operation and observability

Status: implementation in progress on `phase-22-sustained-paper-observability-v2`; final CI gate pending.

Implemented:
- explicit paper-session heartbeats/checkpoints;
- sequence continuity checks so dropped checkpoints are detectable;
- integrity hash on every checkpoint;
- stale-session detection with configurable timeout;
- explicit DEGRADED state when Phase 21 blocks paper entries;
- INVALID state when no valid checkpoint exists;
- safe handling of infinite profit factor in observability output;
- checkpoint retention limit for long-running sessions;
- heartbeat integration into `PaperExecutionLoop` after every market event;
- durable checkpoint persistence and recovery across process restarts;
- read-only dashboard health and checkpoint history;
- end-to-end candidate -> registry -> paper execution -> Phase 21 rollback -> observability recovery test;
- dedicated Phase 22 CI covering observability, dashboard, end-to-end and Phase 21 safety regressions.

Safety boundary:
- observability is read-only with respect to trading authorization;
- it never promotes or edits candidates;
- it never bypasses Phase 21 monitoring;
- it never places live orders;
- stale/invalid observability does not authorize a new trade.

Final gate:
- run the expanded Phase 22 CI;
- fix any regression before marking Phase 22 green;
- after green, begin the sustained end-to-end paper validation period before any live-execution work.
