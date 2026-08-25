import json

import pandas as pd
import streamlit as st

from paper_portfolio import PaperPortfolio
from paper_reporting import build_report, closed_trade_rows, summary_rows
from paper_operations import build_operations_status, event_summary


st.set_page_config(
    page_title="Paper Analytics",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Paper Trading Analytics")
st.caption("Read-only performance reporting for the persistent simulation-only paper portfolio.")

with st.sidebar:
    st.header("Paper session")
    capital = st.number_input("Startkapitaal (€)", 100.0, 100000.0, 1000.0, 100.0)
    risk = st.slider("Risico per trade (%)", 0.25, 2.0, 1.0, 0.25)
    fee = st.number_input("Fee per kant (%)", 0.0, 0.50, 0.10, 0.01)
    slip = st.number_input("Slippage per kant (%)", 0.0, 0.50, 0.03, 0.01)
    symbols = st.multiselect(
        "Paper-symbolen",
        [
            "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
            "ADAUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT", "DOTUSDT",
        ],
        default=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    )

if not symbols:
    st.warning("Selecteer minstens één paper-symbool.")
    st.stop()

portfolio = PaperPortfolio(
    capital=capital,
    risk_pct=risk,
    fee_pct=fee,
    slippage_pct=slip,
    coins=symbols,
    persist=True,
)

report = build_report(portfolio)
summary = report["summary"]
ops = build_operations_status(portfolio)
events = event_summary(portfolio)

health_icon = {"HEALTHY": "🟢", "WATCH": "🟡", "BLOCKED": "🔴"}.get(ops["health"], "⚪")
st.info(
    f"{health_icon} **Session {ops['health']}** · "
    f"ID `{ops['session_id']}` · "
    f"persistentie: {'aan' if ops['persistence_enabled'] else 'uit'} · "
    f"events: {ops['total_events']}"
)

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Equity", f"€{summary['equity']:,.2f}")
c2.metric("Rendement", f"{summary['return_pct']:+.2f}%")
c3.metric("Winrate", f"{summary['win_rate_pct']:.1f}%")
c4.metric("Profit factor", "∞" if summary["profit_factor"] is None else f"{summary['profit_factor']:.2f}")
c5.metric("Expectancy", f"€{summary['expectancy']:+.2f}")
c6.metric("Max DD", f"-{summary['max_drawdown_pct']:.2f}%")

d1, d2, d3, d4, d5, d6 = st.columns(6)
d1.metric("Closed trades", summary["closed_trades"])
d2.metric("LONG", summary["long_trades"])
d3.metric("SHORT", summary["short_trades"])
d4.metric("Gross profit", f"€{summary['gross_profit']:+.2f}")
d5.metric("Gross loss", f"€{summary['gross_loss']:.2f}")
d6.metric("Fees", f"€{summary['total_fees']:.2f}")

st.subheader("Operations")
o1, o2, o3, o4 = st.columns(4)
o1.metric("Accounts", ops["accounts"])
o2.metric("Open positions", ops["open_positions"])
o3.metric("Open events", ops["open_events"])
o4.metric("Blocked accounts", ops["blocked_accounts"])

if ops["daily_risk"]:
    st.dataframe(pd.DataFrame(ops["daily_risk"]), use_container_width=True, hide_index=True)

with st.expander("Event summary"):
    st.json(events)

st.subheader("Performance metrics")
metrics = pd.DataFrame(summary_rows(report))
st.dataframe(metrics, use_container_width=True, hide_index=True)

if report["equity_history"]:
    st.subheader("Equity curve")
    st.line_chart(pd.DataFrame({"Equity": report["equity_history"]}), height=260)

st.subheader("Gesloten trades")
trade_rows = closed_trade_rows(report)
if trade_rows:
    st.dataframe(pd.DataFrame(trade_rows), use_container_width=True, hide_index=True)
else:
    st.info("Nog geen gesloten paper-trades.")

st.subheader("Open posities")
if report["open_positions"]:
    st.dataframe(pd.DataFrame(report["open_positions"]), use_container_width=True, hide_index=True)
else:
    st.info("Geen open paper-posities.")

st.subheader("Exports")
json_payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
json_col, csv_col = st.columns(2)
with json_col:
    st.download_button(
        "⬇️ Download volledig rapport (JSON)",
        data=json_payload,
        file_name="paper_trading_report.json",
        mime="application/json",
        use_container_width=True,
    )
with csv_col:
    csv_data = pd.DataFrame(trade_rows).to_csv(index=False) if trade_rows else ""
    st.download_button(
        "⬇️ Download gesloten trades (CSV)",
        data=csv_data,
        file_name="paper_closed_trades.csv",
        mime="text/csv",
        use_container_width=True,
        disabled=not bool(trade_rows),
    )

st.caption(f"Rapport gegenereerd: {report['generated_at']}")
