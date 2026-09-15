# Crypto DayTrader

Crypto daytrading research and execution framework for **backtesting, paper trading and controlled strategy research**.

## Current reset

The repository is being rebuilt around one accounting and execution path. The previous V3 experiment was removed from the active codebase because it combined multiple overlapping strategy, portfolio-risk, exit and replay layers and produced results that were not economically consistent with the account ledger.

The locked V2 replay remains the historical benchmark. Experimental strategy variants are not promoted merely because they generate more trades.

## Target architecture

```text
MARKET DATA
    ↓
FEATURE ENGINE
    ↓
REGIME / MARKET CONTEXT
    ↓
SIGNAL / SETUP
    ↓
RISK ENGINE
    ↓
PORTFOLIO
    ↓
EXECUTION ENGINE
    ↓
TRADE LEDGER
    ↓
METRICS / FORENSICS
```

### Design rules

1. **One source of truth for execution.** Entry, fills, fees, slippage, position sizing, stops, partials, trailing stops and exits must use the same execution model.
2. **The ledger is accounting truth.** Reported P&L must reconcile to cash, positions, fees and fills.
3. **Research cannot change accounting.** Strategy experiments are evaluated through the same execution and ledger path.
4. **Backtests must be deterministic.** Intrabar ordering, available information and fill assumptions are explicit and tested.
5. **Validation is separated from discovery.** In-sample discovery, out-of-sample validation and promotion gates must not share fitted thresholds.
6. **No live trading by default.** Live execution remains a separate, explicitly controlled release boundary.

## Validation order

1. Clean architecture and dependency audit
2. Synthetic execution/accounting tests
3. Reproduce the locked V2 benchmark
4. Validate data timing and lookahead safety
5. Research new edges
6. Out-of-sample / walk-forward validation
7. Promotion only after predefined gates pass

## Development

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the test suite:

```bash
python -m pytest -q
```

Compile Python sources:

```bash
python -m compileall -q .
```

## Safety

Paper trading and backtesting are research tools, not a guarantee of profitability. Real-money trading must remain disabled until the software, operational controls, exchange integration and risk limits have been independently validated and explicitly approved.
