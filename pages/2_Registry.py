"""Phase 19 candidate registry dashboard.

This page connects the persistent candidate registry to Streamlit without
changing the trading engine. Candidates are imported from the existing
optimizer result store, but promotion and rollback always require an explicit
button click. No live orders are possible from this page.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from candidate_dashboard import candidate_table, registry_snapshot, request_rollback
from candidate_registry import CandidateRegistry


RESULTS_FILE = "optimizer_results_v850.json"
REGISTRY_FILE = "data/candidate_registry.json"

st.set_page_config(page_title="Candidate Registry", page_icon="🧠", layout="wide")

st.title("🧠 Candidate Registry")
st.caption("Phase 19 • auditable strategy versions • paper/research only • geen live orders")

registry = CandidateRegistry(REGISTRY_FILE)


def load_optimizer_results() -> dict:
    path = Path(RESULTS_FILE)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def import_candidates() -> int:
    data = load_optimizer_results()
    results = data.get("results", {})
    if not isinstance(results, dict):
        return 0

    count = 0
    for symbol, payload in results.items():
        if not isinstance(payload, dict):
            continue
        row = payload.get("row", payload)
        if not isinstance(row, dict):
            continue
        status = str(row.get("Status", "")).upper()
        if status not in {"ROBUST", "TRADE"}:
            continue
        candidate = dict(row)
        candidate.setdefault("symbol", symbol)
        candidate["registry_source"] = "optimizer_results_v850"
        registry.register(candidate)
        count += 1
    return count


with st.expander("Optimizer → registry", expanded=True):
    st.write("Importeer ROBUST/TRADE kandidaten uit de bestaande optimizerresultaten.")
    if st.button("📥 Synchroniseer kandidaten", type="secondary"):
        imported = import_candidates()
        st.success(f"{imported} kandidaat/kandidaten gecontroleerd en geregistreerd.")
        st.rerun()

snapshot = registry_snapshot(registry)
active = snapshot["active"]

if active:
    st.success(f"Actieve kandidaat: {snapshot['active_id']} • status {snapshot['active_status']}")
    active_candidate = active.get("candidate", {})
    cols = st.columns(4)
    cols[0].metric("Candidate ID", snapshot["active_id"])
    cols[1].metric("Strategie", active_candidate.get("Strategy", active_candidate.get("label", "-")))
    cols[2].metric("Coin", active_candidate.get("symbol", "-"))
    cols[3].metric("OOS PF", active_candidate.get("OOS PF", "-"))
else:
    st.warning("Er is momenteel geen actieve kandidaat.")

rows = candidate_table(registry)
if rows:
    st.subheader("Geregistreerde kandidaten")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    registered_ids = [row["id"] for row in rows if row.get("status") != "ACTIVE"]
    if registered_ids:
        st.subheader("Handmatige promotie")
        promote_id = st.selectbox("Kandidaat", registered_ids, key="registry_promote_id")
        st.caption("Promotie is een expliciete menselijke beslissing en activeert geen live orders.")
        if st.button("✅ Promoveer geselecteerde kandidaat", type="primary"):
            decision = registry.promote(promote_id, human_approved=True)
            if decision.approved:
                st.success(f"Kandidaat {promote_id} is actief gemaakt.")
            else:
                st.error(f"Promotie geblokkeerd: {decision.reason}")
            st.rerun()

    st.subheader("Rollback")
    rollback_options = ["(deactiveer huidige kandidaat)"] + [row["id"] for row in rows if row.get("status") == "ROLLED_BACK"]
    rollback_target = st.selectbox("Herstel naar", rollback_options, key="registry_rollback_target")
    target_id = None if rollback_target.startswith("(") else rollback_target
    if st.button("↩️ Voer rollback uit"):
        result = request_rollback(registry, target_id)
        st.success(f"Rollback uitgevoerd. Actief: {result['active_id'] or 'NONE'}")
        st.rerun()
else:
    st.info("Nog geen ROBUST/TRADE kandidaten geregistreerd. Voer eerst een optimizer-run uit en synchroniseer daarna.")

st.subheader("Audit trail")
history = snapshot["history"]
if history:
    st.dataframe(pd.DataFrame(history), use_container_width=True, hide_index=True)
else:
    st.caption("Nog geen registry-events.")
