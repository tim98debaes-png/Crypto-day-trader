# Phase 21 — Paper-session monitoring and safe rollback

Status: safety-monitoring foundation green on `phase-21-paper-monitoring-rollback`; orchestration/dashboard integration remains.

Implemented in this phase:
- deterministic paper-session performance monitor;
- minimum-sample protection before rollback decisions;
- WATCH state for soft deterioration;
- conservative rollback triggers using independent performance/risk breaches;
- registry-backed fallback selection only from previously promoted, still quality-approved candidates;
- active-candidate identity check at monitor evaluation time;
- invalid metric and invalid registry state fail closed;
- explicit registry deactivation when no safe fallback exists;
- durable audit events for every monitor decision;
- dedicated Phase 21 CI with compile checks and the Phase 20/21 safety regression suite.

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

Validation:
- Phase 21 dedicated CI run is green;
- compile checks passed;
- 7-file Phase 20/21 safety regression suite passed.
- The repository-wide pytest suite still contains pre-existing Phase 4/5 contract failures unrelated to Phase 21, so those are intentionally outside this green Phase 21 gate.

Next: integrate the monitor at the paper-session orchestration boundary and add dashboard/audit visibility before marking Phase 21 complete.
