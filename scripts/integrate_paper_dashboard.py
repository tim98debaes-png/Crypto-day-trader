"""Inject the functional Phase 5 paper-trading dashboard into app.py.

The dashboard uses public market data and the validated optimizer candidate gate.
It never places live exchange orders.
"""

from pathlib import Path

APP = Path("app.py")
FOOTER_MARKER = "# ============================================================\n# Footer\n# ============================================================"
DASHBOARD_MARKER = "# ---------------- Phase 5 Paper Trading Dashboard ----------------"
SIGNAL_IMPORT = "from signal_engine import generate_signal\n"
EXECUTION_IMPORT = "from paper_execution import PaperExecutionLoop\n"

DASHBOARD = '''# ---------------- Phase 5 Paper Trading Dashboard ----------------
with st.expander("📊 Phase 5 — Paper Trading", expanded=False):
    st.caption("Simulation only • publieke marktdata • gevalideerde signalen • geen live orders")

    symbols = st.multiselect(
        "Paper-symbolen",
        COINS,
        default=COINS[:3],
        key="phase5_symbols",
    )

    phase5_config = (
        float(capital),
        float(risk),
        float(fee),
        float(slip),
        tuple(symbols),
    )
    if st.session_state.get("phase5_config") != phase5_config:
        st.session_state.phase5_config = phase5_config
        st.session_state.phase5_portfolio = PaperPortfolio(
            capital=capital,
            risk_pct=risk,
            fee_pct=fee,
            slippage_pct=slip,
            coins=symbols,
        )
        st.session_state.phase5_loops = {}
        st.session_state.phase5_last_candle = {}

    if "phase5_portfolio" not in st.session_state:
        st.session_state.phase5_portfolio = PaperPortfolio(
            capital=capital,
            risk_pct=risk,
            fee_pct=fee,
            slippage_pct=slip,
            coins=symbols,
        )
    if "phase5_feed" not in st.session_state:
        st.session_state.phase5_feed = BinancePublicFeed()
    if "phase5_loops" not in st.session_state:
        st.session_state.phase5_loops = {}
    if "phase5_last_candle" not in st.session_state:
        st.session_state.phase5_last_candle = {}

    run_cycle = st.button("▶️ Verwerk nieuwe gesloten candles", key="phase5_run_cycle")
    refresh = st.button("🔄 Marktdata vernieuwen", key="phase5_refresh")
    if refresh:
        st.rerun()

    marks = {}
    cycle_rows = []

    for symbol in symbols:
        try:
            snapshot = st.session_state.phase5_feed.snapshot(symbol)
            marks[symbol] = snapshot.price

            account = st.session_state.phase5_portfolio.account(symbol)
            loop = st.session_state.phase5_loops.get(symbol)
            if loop is None or loop.account is not account:
                loop = PaperExecutionLoop(account)
                st.session_state.phase5_loops[symbol] = loop

            candidate = None
            signal_action = "WAIT"
            signal_reason = "geen gevalideerde kandidaat"
            candle_time = None

            saved = active_results.get(symbol, {}) if isinstance(active_results, dict) else {}
            row = saved.get("row", {}) if isinstance(saved, dict) else {}
            if isinstance(row, dict) and row.get("Status") in {"ROBUST", "TRADE"}:
                params = row.get("Strategy Params") or {}
                if isinstance(params, dict):
                    data = build_mtf(symbol, 1000)
                    latest = data.iloc[-1]
                    candle_time = latest.time.isoformat()
                    long_scores, short_scores = make_signals(data, params)
                    candidate = dict(row)
                    candidate["signal_threshold"] = float(row.get("threshold", params.get("threshold", 70)))
                    candidate["rr"] = float(row.get("RR", params.get("rr", 2.0)))
                    generated = generate_signal(
                        candidate,
                        {
                            "long_score": int(long_scores[-1]),
                            "short_score": int(short_scores[-1]),
                            "stop_distance": float(latest.atr) * float(params.get("sl_atr", 1.5)),
                            "rr": float(params.get("rr", 2.0)),
                        },
                    )
                    signal_action = generated.action
                    signal_reason = generated.reason

                    expected_direction = str(row.get("Direction", "")).upper()
                    if generated.action != expected_direction:
                        candidate = None

            if run_cycle and candle_time is not None:
                if st.session_state.phase5_last_candle.get(symbol) != candle_time:
                    strategy_params = row.get("Strategy Params") or {}
                    market = {
                        "symbol": symbol,
                        "direction": str(row.get("Direction", "LONG")).upper(),
                        "price": float(snapshot.price),
                        "stop_distance": float(latest.atr) * float(strategy_params.get("sl_atr", 1.5)),
                        "rr": float(row.get("RR", strategy_params.get("rr", 2.0))),
                        "timestamp": candle_time,
                    }
                    result = loop.on_market(market, candidate=candidate)
                    st.session_state.phase5_last_candle[symbol] = candle_time
                else:
                    result = {"action": "SKIP", "reason": "candle already processed"}
            else:
                result = {"action": "PREVIEW", "reason": "druk op verwerk om paper execution te activeren"}

            cycle_rows.append({
                "Symbol": symbol,
                "Signal": signal_action,
                "Execution": result.get("action", ""),
                "Reason": result.get("reason", signal_reason),
                "Price": round(float(snapshot.price), 8),
                "Position": account.position.direction if account.position else "-",
            })
        except Exception as exc:
            cycle_rows.append({
                "Symbol": symbol,
                "Signal": "ERROR",
                "Execution": "ERROR",
                "Reason": str(exc),
                "Price": marks.get(symbol, 0),
                "Position": "-",
            })

    summary = st.session_state.phase5_portfolio.summary(marks)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Equity", f"€{summary['equity']:,.2f}")
    c2.metric("Open posities", summary["open_positions"])
    c3.metric("Closed trades", summary["closed_trades"])
    c4.metric("Winrate", f"{summary['win_rate_pct']:.1f}%")
    c5.metric("Profit factor", "∞" if summary["profit_factor"] == float("inf") else f"{summary['profit_factor']:.2f}")

    if cycle_rows:
        st.dataframe(pd.DataFrame(cycle_rows), use_container_width=True, hide_index=True)

    positions = []
    for symbol, account in st.session_state.phase5_portfolio.accounts.items():
        if account.position is not None:
            position = account.position
            positions.append({
                "Symbol": symbol,
                "Direction": position.direction,
                "Entry": position.entry_price,
                "Quantity": position.quantity,
                "Stop": position.stop_price,
                "Target": position.target_price,
                "Entry fee": position.entry_fee,
            })

    if positions:
        st.subheader("Open paper-posities")
        st.dataframe(pd.DataFrame(positions), use_container_width=True, hide_index=True)

    events = st.session_state.phase5_portfolio.audit_log()
    if events:
        st.subheader("Paper audit log")
        st.dataframe(pd.DataFrame(events[-20:]), use_container_width=True, hide_index=True)
    else:
        st.info("Nog geen paper-transacties. De engine wacht op een gevalideerde kandidaat én een nieuw gesloten candle.")

'''


def main():
    text = APP.read_text(encoding="utf-8")

    if EXECUTION_IMPORT not in text:
        if SIGNAL_IMPORT not in text:
            raise SystemExit("signal_engine import marker not found")
        text = text.replace(SIGNAL_IMPORT, SIGNAL_IMPORT + EXECUTION_IMPORT, 1)

    if DASHBOARD_MARKER in text:
        start = text.index(DASHBOARD_MARKER)
        end = text.index(FOOTER_MARKER, start)
        text = text[:start] + DASHBOARD + text[end:]
    else:
        if FOOTER_MARKER not in text:
            raise SystemExit("Footer marker not found")
        text = text.replace(FOOTER_MARKER, DASHBOARD + FOOTER_MARKER, 1)

    APP.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
