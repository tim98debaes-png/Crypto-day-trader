# Run #72 code audit

## Evidence
Run #72 was the first one-hour paper run after the direction-aware portfolio-selection fix. It produced three closed ENAUSDT trades: LONG loss, SHORT win, LONG loss. The repeated ENA re-entry was the clearest strategy/execution issue. The first losing trade also exceeded its intended risk materially because the paper loop closed at the sampled market price after the stop had been crossed.

## Findings

### Fixed
1. **Per-symbol re-entry churn** — a closed asset could immediately re-enter in the opposite direction and then re-enter again. `PaperAccount` now maintains per-symbol cooldowns: 15 minutes after a loss and 5 minutes after a profitable close. This is intentionally asset-local rather than a global trading halt.
2. **Stop/target sampling artifact** — the paper execution loop previously used the current sampled price when a stop/target condition was detected. With 30-second polling, a price can cross a stop between samples and create an artificial oversized loss. Stop and target fills now use the deterministic trigger price; execution-gap diagnostics are retained separately.
3. **Risk configuration duplication** — the normal paper risk percentage is now sourced from `RiskConfig.standard_risk_pct` rather than a second hard-coded constant.
4. **Regression coverage** — tests now cover loss cooldown, stop-trigger fills, and risk-to-actual accounting.

### Reviewed and retained
- Maximum four open positions and four-percent aggregate open risk.
- Sector and correlation concentration controls.
- Direction-aware portfolio selection introduced in PR #19.
- Daily loss guard and runtime entry guard.
- Partial take-profit before trailing.
- 360-minute time stop; unchanged because it is a safety backstop rather than a 15/60-minute strategy exit.
- Belgian tax bookkeeping remains review-oriented; crypto tax classification is deliberately not hard-coded as a legal conclusion.

### Follow-up items requiring more data, not blind parameter changes
1. **Entry quality**: 95 five-factor-ready events in run #72 are not enough to establish predictive value. Future runs should log outcomes by factor/bounce component and direction.
2. **Fees**: the paper engine uses 0.10% per side. This is conservative for a research model but must be matched to the eventual venue/account tier before judging net profitability.
3. **Volatility feature**: scanner volatility is based on the maximum sampled move, not a standard deviation/ATR estimate. This should be compared against realized trade outcomes before replacing it.
4. **Correlation window**: six observations is intentionally conservative but statistically small. It should be treated as a concentration heuristic, not a predictive correlation model.
5. **Market-feed resilience**: the live paper workflow correctly records provider fallback/errors; the strategy should not be considered validated until a meaningful sample spans both normal and degraded feed conditions.

## Validation rule
No production/live-money promotion is justified by run #72. The next validation should be CI-green followed by a fresh paper run long enough to produce a materially larger closed-trade sample, with special attention to re-entry count, stop execution gap, risk-to-actual ratio, and per-direction results.
