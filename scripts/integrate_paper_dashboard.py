"""Add the safe Phase 5 paper dashboard to app.py.

The dashboard is deliberately read-only with respect to exchanges. It shows
paper-account state and public prices; it never creates live orders.
"""

from pathlib import Path

APP = Path("app.py")
MARKER = "# ============================================================\n# Footer\n# ============================================================"
IMPORT_MARKER = "from signal_engine import generate_signal\n"
IMPORT = "from paper_portfolio import PaperPortfolio\nfrom market_feed import BinancePublicFeed\n"
DASHBOARD_MARKER = "# ---------------- Phase 5 Paper Trading Dashboard ----------------"

DASHBOARD = '''# ---------------- Phase 5 Paper Trading Dashboard ----------------\nwith st.expander("📊 Phase 5 — Paper Trading", expanded=False):\n    st.caption("Simulation only • publieke marktdata • geen live orders")\n\n    if "phase5_portfolio" not in st.session_state:\n        st.session_state.phase5_portfolio = PaperPortfolio(\n            capital=capital,\n            risk_pct=risk,\n            fee_pct=fee,\n            slippage_pct=slip,\n        )\n\n    if "phase5_feed" not in st.session_state:\n        st.session_state.phase5_feed = BinancePublicFeed()\n\n    symbols = st.multiselect(\n        "Paper-symbolen",\n        COINS,\n        default=COINS[:3],\n        key="phase5_symbols",\n    )\n\n    if st.button("🔄 Marktdata vernieuwen", key="phase5_refresh"):\n        st.rerun()\n\n    marks = {}\n    for symbol in symbols:\n        try:\n            marks[symbol] = st.session_state.phase5_feed.snapshot(symbol).price\n        except Exception as exc:\n            st.warning(f"{symbol}: marktdata niet beschikbaar ({exc})")\n\n    summary = st.session_state.phase5_portfolio.summary(marks)\n    c1, c2, c3, c4 = st.columns(4)\n    c1.metric("Equity", f"€{summary['equity']:,.2f}")\n    c2.metric("Open posities", summary["open_positions"])\n    c3.metric("Closed trades", summary["closed_trades"])\n    c4.metric("Winrate", f"{summary['win_rate_pct']:.1f}%")\n\n    if marks:\n        st.dataframe(\n            pd.DataFrame(\n                [{"Symbol": symbol, "Price": price} for symbol, price in marks.items()]\n            ),\n            use_container_width=True,\n            hide_index=True,\n        )\n\n    st.info("De koppeling van gevalideerde optimizer-signalen naar automatische paper entries blijft actief via de Phase-5 execution engine.")\n\n'''


def main():
    text = APP.read_text(encoding="utf-8")
    if DASHBOARD_MARKER in text:
        return

    if IMPORT not in text:
        if IMPORT_MARKER not in text:
            raise SystemExit("signal_engine import marker not found")
        text = text.replace(IMPORT_MARKER, IMPORT_MARKER + IMPORT, 1)

    if MARKER not in text:
        raise SystemExit("Footer marker not found")

    text = text.replace(MARKER, DASHBOARD + MARKER, 1)
    APP.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
