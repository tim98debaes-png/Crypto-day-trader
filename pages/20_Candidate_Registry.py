"""Streamlit page for the registry-backed active candidate view."""
import streamlit as st

from candidate_dashboard_view import build_candidate_dashboard, build_candidate_rows
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

st.subheader("Registered candidates")
rows = build_candidate_rows(registry)
if rows:
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.info("No candidates registered yet.")

st.info("This page is read-only. Promotion and rollback remain controlled by the Candidate Registry workflow.")
