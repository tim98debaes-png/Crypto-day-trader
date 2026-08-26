# Changelog

## Unreleased / Phase 33

### Release hardening
- Added Phase 33 release-hardening smoke tests.
- Added release-manifest validation to Main Release CI.
- Verified Phase 31 end-to-end contracts remain covered by CI.
- Verified Phase 32 dashboard, serialization, Streamlit renderer, and application adapter contracts remain covered by CI.
- Confirmed dashboard snapshots are immutable and degraded-state alerts are deterministic.
- Removed the temporary Phase 32 CI-trigger marker.

### Validation
- Main Release CI run #50 completed successfully on commit `30c156a9dfeb172748af7cd5d008637b07f97cec`.
- Full test suite and Phase 33 release-hardening checks are currently part of the main validation pipeline.

## Versioning

The application currently reports version `8.5.0` from `app.py`.

No live trading capability is introduced by these release-hardening changes; the application remains research/paper-trading oriented.
