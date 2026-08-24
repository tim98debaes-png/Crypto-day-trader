# Phase 12 — Paper session alerts and safety thresholds

## Goal
Turn the stable Phase 9/10/11 operational and lifecycle contracts into deterministic, configurable alerts without coupling alerting to execution.

## Included
- Read-only alert engine for session lifecycle, stale activity and daily-loss thresholds.
- Configurable warning/critical thresholds.
- Critical alerts for stopped/unknown sessions and breached daily-loss protection.
- Warning alerts for paused sessions, approaching daily-loss limits and stale activity.
- Deterministic ordering and deduplication for dashboard/notifier consumers.
- Dedicated regression tests and CI coverage.

## Safety
Alerts do not mutate portfolio state, resume sessions, pause sessions automatically, or place exchange orders. The system remains simulation-only.
