# Phase 21 — Paper-session monitoring and safe rollback

Status: implementation complete; final dedicated CI run pending/validating on `phase-21-paper-monitoring-rollback`.

Implemented:
- deterministic paper-session performance monitor;
- minimum-sample protection before rollback decisions;
- WATCH state for soft deterioration;
- conservative rollback triggers using independent performance/risk breaches;
- registry-backed fallback selection only from previously promoted, still quality-approved candidates;
- active-candidate identity check at monitor evaluation time;
- invalid metric and invalid registry state fail closed;
- explicit registry deactivation when no safe fallback exists;
- durable audit events for every monitor decision;
- real paper-account metric adapters;
- monitor integrated into `PaperExecutionLoop` before every new paper entry;
- existing positions remain exit-manageable after a rollback/block;
- monitor status, breaches, metrics and audit trail exposed in the Candidate Registry UI;
- dedicated Phase 21 CI covering monitoring, execution-boundary and dashboard regressions.

Safety boundary:
- paper simulation only;
- the monitor never promotes a candidate;
- the monitor never creates or modifies candidate parameters;
- the monitor never places live orders;
- no safe fallback means no active candidate, so the Phase 20 execution gate blocks new entries.

Rollback policy:
- fewer than 20 closed trades is insufficient evidence and does not trigger rollback;
- soft deterioration enters WATCH;
- rollback requires two independent hard performance breaches, or a severe drawdown/loss-streak breach;
- only an existing ROLLED_BACK candidate that still passes the production paper quality gate may be restored;
- a failed or ambiguous rollback verification fails closed.

Final gate:
- previous Phase 21 safety suite was green;
- the new final CI adds execution-boundary integration and dashboard coverage;
- Phase 21 will only be marked fully green after that run completes successfully.
- Repository-wide historical Phase 4/5 failures remain separate from the Phase 21 safety gate.

Next phase after green: Phase 22 should focus on sustained paper-session operation/observability and then a full end-to-end paper validation cycle before any consideration of live execution.
