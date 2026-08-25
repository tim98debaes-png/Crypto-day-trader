# Phase 6 status

## Persistent paper trading state

Phase 6 adds a persistence layer around the existing simulation-only paper portfolio.

Implemented:
- atomic JSON state writes using a temporary file + replace;
- configuration fingerprinting so incompatible portfolio configurations never restore old state;
- restoration of cash, risk settings, daily-loss state, open positions and audit history;
- restoration of equity history, peak equity and maximum drawdown;
- bounded state history to prevent unbounded local-file growth;
- automatic persistence when `PaperPortfolio` is created from an active Streamlit run;
- explicit `save_state()` API for future UI/export integrations;
- regression tests for closed trades, open positions and incompatible configurations;
- CI coverage for Phase 6.

## Important deployment note

The current implementation persists to the local application filesystem. This survives Streamlit process/rerun restarts when that filesystem remains available, but a platform redeploy/container replacement may reset local files. A later phase can move the same serialized state format to durable external storage without changing the paper engine itself.

Live exchange order placement remains disabled.
