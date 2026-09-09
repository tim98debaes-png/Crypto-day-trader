# Paper-parity research protocol

## Goal

The historical benchmark must test the strategy that the paper runner actually executes. Parameter optimization is not meaningful until this parity layer passes its invariants.

## Replay clock

- Historical candles: **1 minute**.
- A signal may use only completed candles up to the current timestamp.
- A new entry is queued at the completed-bar close and filled at the next available bar open.
- Missing bars do not create synthetic fills.
- The 1m source is the closest public OHLC approximation to the live runner's 30-second polling cadence; it is not presented as tick-level reconstruction.

## Entry

The replay reuses `entry_signal_details()` rather than recreating its five-factor logic. This preserves the current trend, price-location, momentum, microstructure, pullback and bounce-confirmation rules.

Candidate ranking uses the same scanner universe and liquidity floor. For historical data, 24h quote volume is reconstructed from the preceding 1,440 one-minute bars. The rolling scanner history is capped at 20 observations, matching the live paper runner's history cap.

## Regime and BTC variants

Three modes use exactly the same execution engine:

1. `PAPER`: current paper entry/exit logic only.
2. `REGIME`: `PAPER` plus the established 1h directional regime gate.
3. `REGIME_BTC`: `REGIME` plus the established BTC context gate.

The BTC gate blocks LONG when BTC is confirmed downtrend/high-volatility and blocks SHORT when BTC is confirmed uptrend/high-volatility. BTC range is allowed for either direction.

## Execution

`PaperAccount` remains the source of truth for:

- fee-aware position sizing;
- 0.10% fee per side;
- 0.02% slippage per side;
- daily loss protection;
- total open-risk cap;
- maximum open positions;
- sector and correlation constraints;
- loss/win re-entry cooldowns;
- partial profit;
- trailing stop;
- time stop.

Hard stop/target events are evaluated against OHLC. When a single historical bar crosses both a stop and a profit trigger, the stop is assumed to occur first because OHLC does not reveal the intrabar path. This is deliberately conservative.

## Validation ladder

A strategy change is not promoted merely because one backtest is profitable.

1. **Unit/parity tests** — signal, regime/BTC gates, sizing and replay invariants.
2. **Historical replay** — PAPER vs REGIME vs REGIME_BTC on identical 1m data.
3. **Trade-level diagnostics** — exits, direction, symbols, streaks, stop gaps, fees and risk-to-actual loss.
4. **Walk-forward/OOS** — untouched acceptance criteria.
5. **Monte Carlo / robustness** — untouched acceptance criteria.
6. **Paper session** — live market observation after research evidence passes.

No threshold, optimizer, risk or robustness criterion may be changed merely to make the result pass.
