"""Inject the Phase 5 paper-trading dashboard into app.py.

The patch is narrow and idempotent. It reuses the existing optimizer output,
MTF indicators and shared signal engine. It only creates simulated positions.
"""

from pathlib import Path

APP = Path("app.py")
IMPORT_MARKER = "from signal_engine import generate_signal\n"
IMPORT_INSERT = "from paper_portfolio import PaperPortfolio\n"
TAB_OLD = '''tab1, tab2, tab3, tab4 = st.tabs(\n    [\n        "🔬 Optimizer",\n        "🧠 Strategy Discovery",\n        "🏆 Robustness",\n        "📈 Live scanner",\n    ]\n)'''
TAB_NEW = '''tab1, tab2, tab3, tab4, tab5 = st.tabs(\n    [\n        "🔬 Optimizer",\n        "🧠 Strategy Discovery",\n        "🏆 Robustness",\n        "📈 Live scanner",\n        "📊 Paper Trading",\n    ]\n)'''
FOOTER_MARKER = '''# ============================================================\n# Footer\n# ============================================================'''

PAPER_BLOCK = '''# ============================================================\n# Paper Trading\n# ============================================================\n\nwith tab5:\n    st.subheader("📊 Paper Trading")\n    st.write(\n        "Simuleer de bestaande gevalideerde strategie met gesloten 5m-candles. "\n        "Er worden nooit echte exchange-orders geplaatst."\n    )\n\n    paper_candidates = {}\n    for symbol in COINS:\n        saved = (\n            active_results\n            .get(symbol, {})\n            .get("row", {})\n        )\n        if isinstance(saved, dict) and saved.get("Status") in {"ROBUST", "TRADE"}:\n            paper_candidates[symbol] = saved\n\n    if not paper_candidates:\n        st.info("Voer eerst de optimizer uit en zorg dat minstens één kandidaat ROBUST is.")\n    else:\n        paper_coins = st.multiselect(\n            "Paper coins",\n            list(paper_candidates.keys()),\n            default=list(paper_candidates.keys())[:3],\n            key="paper_coins",\n        )\n\n        paper_capital = st.number_input(\n            "Paper startkapitaal (€)",\n            100.0,\n            100000.0,\n            1000.0,\n            100.0,\n            key="paper_capital",\n        )\n\n        col_a, col_b = st.columns(2)\n        with col_a:\n            if st.button("▶️ Start / hervat paper trading", type="primary", key="paper_start"):\n                st.session_state["paper_portfolio"] = PaperPortfolio(\n                    total_capital=paper_capital,\n                    coins=paper_coins,\n                )\n                st.session_state["paper_portfolio"].running = True\n                st.rerun()\n        with col_b:\n            if st.button("⏹️ Stop paper trading", key="paper_stop"):\n                portfolio = st.session_state.get("paper_portfolio")\n                if portfolio is not None:\n                    portfolio.running = False\n\n        portfolio = st.session_state.get("paper_portfolio")\n\n        if portfolio is None:\n            st.info("Start de paper trader om een simulatiesessie te openen.")\n        else:\n            @st.fragment(run_every=300)\n            def paper_tick():\n                portfolio = st.session_state.get("paper_portfolio")\n                if portfolio is None or not portfolio.running:\n                    st.caption("Paper trader staat stil.")\n                    return\n\n                scan_rows = []\n                for symbol in list(paper_coins):\n                    candidate = paper_candidates.get(symbol)\n                    if not candidate:\n                        continue\n\n                    params = candidate.get("Strategy Params")\n                    if not isinstance(params, dict):\n                        scan_rows.append({"Coin": symbol, "Action": "WAIT", "Reason": "Geen Strategy Params"})\n                        continue\n\n                    try:\n                        params = dict(params)\n                        params["family"] = str(params.get("family", candidate.get("Strategy", "trend"))).lower()\n                        params["direction"] = candidate.get("Direction", params.get("direction", "LONG"))\n\n                        # Paper execution must use fresh closed-candle data.\n                        build_mtf.clear()\n                        data = build_mtf(symbol, 1000)\n                        long_scores, short_scores = make_signals(data, params)\n                        latest = data.iloc[-1]\n\n                        market = {\n                            "symbol": symbol,\n                            "price": float(latest.close),\n                            "timestamp": pd.Timestamp(latest.time).isoformat(),\n                        }\n                        indicators = {\n                            "long_score": int(long_scores[-1]),\n                            "short_score": int(short_scores[-1]),\n                            "stop_distance": float(latest.atr) * float(params.get("sl_atr", 1.5)),\n                            "rr": float(params.get("rr", 2.0)),\n                        }\n\n                        result = portfolio.process(symbol, candidate, market, indicators)\n                        scan_rows.append({\n                            "Coin": symbol,\n                            "Action": result.get("action"),\n                            "Reason": result.get("reason", ""),\n                            "Price": round(float(latest.close), 8),\n                            "Long": indicators["long_score"],\n                            "Short": indicators["short_score"],\n                        })\n                    except Exception as exc:\n                        scan_rows.append({"Coin": symbol, "Action": "ERROR", "Reason": str(exc)})\n\n                totals = portfolio.totals()\n                m1, m2, m3, m4 = st.columns(4)\n                m1.metric("Equity", f"€{totals['equity']:.2f}")\n                m2.metric("Return", f"{totals['return_pct']:.2f}%")\n                m3.metric("Closed trades", totals["closed_trades"])\n                m4.metric("Winrate", f"{totals['win_rate_pct']:.1f}%")\n\n                st.dataframe(pd.DataFrame(portfolio.rows()), use_container_width=True, hide_index=True)\n                st.caption(f"Laatste paper-candlecheck: {pd.Timestamp.now(tz='UTC').isoformat()}")\n                if scan_rows:\n                    st.dataframe(pd.DataFrame(scan_rows), use_container_width=True, hide_index=True)\n\n                events = portfolio.trade_log()\n                if events:\n                    st.subheader("Trade audit log")\n                    st.dataframe(pd.DataFrame(events), use_container_width=True, hide_index=True)\n\n            paper_tick()\n\n'''


def main():
    text = APP.read_text(encoding="utf-8")

    if IMPORT_INSERT not in text:
        if IMPORT_MARKER not in text:
            raise SystemExit("signal_engine import marker not found")
        text = text.replace(IMPORT_MARKER, IMPORT_MARKER + IMPORT_INSERT, 1)

    if TAB_OLD in text:
        text = text.replace(TAB_OLD, TAB_NEW, 1)
    elif TAB_NEW not in text:
        raise SystemExit("expected tab definition not found")

    if 'with tab5:\n    st.subheader("📊 Paper Trading")' not in text:
        if FOOTER_MARKER not in text:
            raise SystemExit("footer marker not found")
        text = text.replace(FOOTER_MARKER, PAPER_BLOCK + FOOTER_MARKER, 1)

    APP.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
