# Paper-parity research protocol

## Goal

The historical benchmark must test the strategy that the paper runner actually executes. Parameter optimization is not meaningful until this parity layer passes its invariants.

## Replay clock

- Historical candles: **1 minute**.
- A signal may use only completed candles up to the current timestamp.
- A new entry is queued at completed-bar close and filled at the next available bar open.
- Missing bars do not create synthetic fills.
- 1m OHLC is the closest practical public-data approximation to the live runner's 30-second polling cadence; it is not claimed to be tick-level reconstruction.

## Entry and scanner

The replay reuses `entry_signal_details()` rather than recreating its five-factor logic. This preserves the current trend, price-location, momentum, microstructure, pullback and bounce-confirmation rules.

Candidate ranking uses the same liquid universe and $5M liquidity floor. Historical 24h quote volume is reconstructed from the preceding 1,440 one-minute bars. The scanner history is capped at 20 observations, matching the live paper runner.

## Three controlled modes

1. **PAPER** — current paper entry/exit lifecycle, including the simple BTC 20-EMA directional gate already used by the live paper runner.
2. **REGIME** — `PAPER` plus the established 1h asset regime gate: directional EMA order, ADX >= 18 and volatility regime <= 3.
3. **REGIME_BTC** — `REGIME` plus the established 1h BTC context gate. LONG is blocked by confirmed BTC downtrend/high volatility; SHORT is blocked by confirmed BTC uptrend/high volatility; BTC range is allowed for either side.

The modes use exactly the same execution engine and historical bars. Only the named filter changes.

## Execution

`PaperAccount` remains the source of truth for fee-aware sizing, 0.10% fee per side, 0.02% slippage per side, daily-loss protection, total open-risk cap, maximum positions, sector/correlation constraints, re-entry cooldowns, partial profit and trailing stops.

A 360-minute time stop is also preserved.

Hard stop/target events are evaluated against OHLC. When a single historical bar crosses both a stop and a profit trigger, the stop is assumed to occur first because OHLC does not reveal the intrabar path. This is deliberately conservative.

## Validation ladder

1. Unit/parity tests.
2. Historical replay: PAPER vs REGIME vs REGIME_BTC on identical 1m data.
3. Trade-level diagnostics: exit reason, direction, symbol, streaks, stop gaps, fees and risk-to-actual loss.
4. Walk-forward/OOS using the existing acceptance criteria.
5. Monte Carlo/robustness using the existing acceptance criteria.
6. Paper session only after research evidence passes.

No threshold, optimizer, risk setting or robustness criterion may be changed merely to make the result pass.
