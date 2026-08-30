# Step 1 — Entry/exit timing audit

## Canonical execution contract

The research backtester treats every strategy signal as a decision made from a **completed candle**.

- `LONG` / `SHORT`: execute at the **next candle open for that symbol**.
- `CLOSE`: execute at the **next candle open for that symbol**.
- A signal on the final available candle is not executed because there is no subsequent open.
- Stop-loss and take-profit remain **intrabar** exits using the high/low of a candle in which the position is already open.
- If both SL and TP are touched inside the same candle, the backtester chooses SL conservatively because OHLC data does not reveal the intrabar order.
- If a candle opens through an existing SL or TP, the exit executes at the **candle open**, not at the stale stop/target price.
- Candle OHLC is validated before execution; open and close must lie inside high/low and all prices must be positive.

## Why

Using the signal candle's close as its execution price creates look-ahead bias when the signal itself was calculated from that candle's closing information. Next-open execution makes the benchmark reproducible without assuming a fill that was known before the candle closed.

## Regression coverage

`tests/test_multi_position_backtest.py` verifies:

1. multiple symbols can hold positions simultaneously;
2. entry uses the next candle open rather than the signal candle close;
3. final-candle signals remain unexecuted;
4. signal-driven closes use the next candle open;
5. intrabar stops work even when the candle closes back above the stop;
6. simultaneous SL/TP touches resolve conservatively to SL;
7. long stop gaps execute at the open;
8. short target gaps execute at the open;
9. invalid OHLC is rejected.

No strategy parameters, risk limits, or signal logic are changed by Step 1.
