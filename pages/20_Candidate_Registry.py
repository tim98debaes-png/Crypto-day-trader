"""Streamlit page for the registry-backed active candidate and Phase 21 monitor view."""
import streamlit as st

from candidate_dashboard_view import build_candidate_dashboard, build_candidate_rows, build_monitor_dashboard
from candidate_registry import CandidateRegistry


st.set_page_config(page_title="Candidate Registry", page_icon="🧠", layout="wide")
st.title("🧠 Candidate Registry")
st.caption("Read-only view of the strategy candidate authorized for paper trading.")

registry = CandidateRegistry()
symbol = st.selectbox(
    "Paper symbol",
    ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT", "DOTUSDT"],
)

view = build_candidate_dashboard(registry, symbol)
monitor = build_monitor_dashboard(registry)

if view["allowed"]:
    st.success(f"ACTIVE · {view['active_candidate_id']}")
    candidate = view["candidate"] or {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OOS return", f"{candidate.get('OOS %', 0):.2f}%")
    c2.metric("OOS profit factor", f"{candidate.get('OOS PF', 0):.2f}")
    c3.metric("OOS trades", str(candidate.get('OOS trades', 0)))
    c4.metric("OOS drawdown", f"{candidate.get('OOS DD', 0):.2f}%")
else:
    st.warning(f"Paper entry blocked: {view['reason']}")

st.subheader("🛡️ Phase 21 paper-session monitor")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Monitor", monitor["status"])
m2.metric("Entries", "ALLOWED" if monitor["allow_new_entries"] else "BLOCKED")
m3.metric("Active", monitor["active_id"] or "NONE")
m4.metric("Fallback", monitor["target_id"] or "—")
if monitor["reason"] != "no_monitor_data":
    st.caption(f"Reason: `{monitor['reason']}`")
if monitor["breaches"]:
    st.warning("Breaches: " + ", ".join(monitor["breaches"]))
if monitor["metrics"]:
    metrics = monitor["metrics"]
    a1, a2, a3, a4, a5 = st.columns(5)
    a1.metric("Closed trades", int(metrics.get("closed_trades", 0)))
    a2.metric("Profit factor", f"{metrics.get('profit_factor', 0):.2f}")
    a3.metric("Return", f"{metrics.get('return_pct', 0):.2f}%")
    a4.metric("Max DD", f"{metrics.get('max_drawdown_pct', 0):.2f}%")
    a5.metric("Loss streak", int(metrics.get("consecutive_losses", 0)))

with st.expander("Monitor audit trail", expanded=False):
    if monitor["events"]:
        st.dataframe(monitor["events"], use_container_width=True, hide_index=True)
    else:
        st.info("No monitor decisions recorded yet.")

st.subheader("Registered candidates")
rows = build_candidate_rows(registry)
if rows:
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.info("No candidates registered yet.")

st.info("This page is read-only. Promotion and rollback remain controlled by the Candidate Registry workflow; the Phase 21 monitor acts only on paper-session health.")
