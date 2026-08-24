from pathlib import Path

APP = Path("app.py")

text = APP.read_text(encoding="utf-8")

old_metrics = '''        summary = st.session_state.phase5_portfolio.summary(marks)\n        c1, c2, c3, c4, c5 = st.columns(5)\n        c1.metric("Equity", f"€{summary['equity']:,.2f}")\n        c2.metric("Open posities", summary["open_positions"])\n        c3.metric("Closed trades", summary["closed_trades"])\n        c4.metric("Winrate", f"{summary['win_rate_pct']:.1f}%")\n        c5.metric("Profit factor", "∞" if summary["profit_factor"] == float("inf") else f"{summary['profit_factor']:.2f}")\n\n'''

new_metrics = '''        summary = st.session_state.phase5_portfolio.summary(marks)\n        c1, c2, c3, c4, c5, c6 = st.columns(6)\n        c1.metric("Equity", f"€{summary['equity']:,.2f}")\n        c2.metric("Rendement", f"{summary['return_pct']:+.2f}%")\n        c3.metric("Open posities", summary["open_positions"])\n        c4.metric("Closed trades", summary["closed_trades"])\n        c5.metric("Winrate", f"{summary['win_rate_pct']:.1f}%")\n        c6.metric("Profit factor", "∞" if summary["profit_factor"] == float("inf") else f"{summary['profit_factor']:.2f}")\n\n        d1, d2, d3, d4 = st.columns(4)\n        d1.metric("Peak equity", f"€{summary['peak_equity']:,.2f}")\n        d2.metric("Current DD", f"-{summary['current_drawdown_pct']:.2f}%")\n        d3.metric("Max DD", f"-{summary['max_drawdown_pct']:.2f}%")\n        d4.metric("Gem. trade", f"€{summary['avg_trade']:+.2f}")\n\n        if len(st.session_state.phase5_portfolio.equity_history) >= 2:\n            equity_frame = pd.DataFrame(\n                {\n                    "Equity": st.session_state.phase5_portfolio.equity_history\n                }\n            )\n            st.caption("Equity curve — elke verwerkte paper-markering")\n            st.line_chart(equity_frame, height=220)\n\n'''

if old_metrics not in text:
    raise SystemExit("Phase 7 metrics anchor not found")
text = text.replace(old_metrics, new_metrics, 1)

old_events = '''        events = st.session_state.phase5_portfolio.audit_log()\n        if events:\n            st.subheader("Paper audit log")\n            st.dataframe(pd.DataFrame(events[-20:]), use_container_width=True, hide_index=True)\n        else:\n            st.info("Nog geen paper-transacties. De engine wacht op een gevalideerde kandidaat én een nieuw gesloten candle.")\n'''

new_events = '''        events = st.session_state.phase5_portfolio.audit_log()\n        closed_events = [event for event in events if event.get("event") == "CLOSE"]\n        if closed_events:\n            st.subheader("Gesloten trades")\n            trade_rows = []\n            for event in closed_events[-20:]:\n                trade_rows.append({\n                    "Tijd": event.get("timestamp", ""),\n                    "Symbol": event.get("symbol", ""),\n                    "Direction": event.get("direction", ""),\n                    "Exit": event.get("price", 0),\n                    "P&L": event.get("pnl", 0),\n                    "Reason": event.get("reason", ""),\n                })\n            st.dataframe(pd.DataFrame(trade_rows), use_container_width=True, hide_index=True)\n\n        if events:\n            st.subheader("Paper audit log")\n            st.dataframe(pd.DataFrame(events[-20:]), use_container_width=True, hide_index=True)\n        else:\n            st.info("Nog geen paper-transacties. De engine wacht op een gevalideerde kandidaat én een nieuw gesloten candle.")\n'''

if old_events not in text:
    raise SystemExit("Phase 7 trade-history anchor not found")
text = text.replace(old_events, new_events, 1)

APP.write_text(text, encoding="utf-8")
print("Phase 7 dashboard patch applied")
