import io
import pandas as pd
import streamlit as st

from optimizer_dashboard import optimize_candles, walk_forward_candles

st.set_page_config(page_title="Strategy Optimizer", page_icon="⚙️", layout="wide")
st.title("⚙️ Strategy Optimizer")
st.caption("Historical paper backtesting only — no live orders are placed.")

with st.expander("Input format", expanded=True):
    st.write("Upload CSV candles with: timestamp, close, long_score, short_score, stop_distance. symbol is optional.")
    st.write("The optimizer searches signal threshold and risk/reward (RR) combinations.")

uploaded = st.file_uploader("Historical candles CSV", type=["csv"])
col1, col2, col3, col4 = st.columns(4)
threshold_min = col1.number_input("Threshold min", min_value=0.1, value=1.0, step=0.1)
threshold_max = col2.number_input("Threshold max", min_value=0.1, value=2.0, step=0.1)
rr_min = col3.number_input("RR min", min_value=0.1, value=1.5, step=0.1)
rr_max = col4.number_input("RR max", min_value=0.1, value=3.0, step=0.1)

col5, col6, col7 = st.columns(3)
threshold_steps = col5.number_input("Threshold steps", min_value=1, max_value=50, value=5)
rr_steps = col6.number_input("RR steps", min_value=1, max_value=50, value=4)
top_n = col7.number_input("Top results", min_value=1, max_value=50, value=10)

run = st.button("Run optimization", type="primary", disabled=uploaded is None)

if uploaded is not None:
    frame = pd.read_csv(io.BytesIO(uploaded.getvalue()))
    required = {"timestamp", "close", "long_score", "short_score", "stop_distance"}
    missing = sorted(required - set(frame.columns))
    if missing:
        st.error("Missing required columns: " + ", ".join(missing))
    else:
        frame["timestamp"] = frame["timestamp"].astype(str)
        candles = frame.to_dict("records")
        st.info(f"Loaded {len(candles):,} candles.")

        if run:
            if threshold_max < threshold_min or rr_max < rr_min:
                st.error("Maximum values must be greater than or equal to minimum values.")
            elif len(candles) < 4:
                st.error("At least 4 candles are required for optimization.")
            else:
                thresholds = [float(x) for x in __import__("numpy").linspace(threshold_min, threshold_max, int(threshold_steps))]
                rrs = [float(x) for x in __import__("numpy").linspace(rr_min, rr_max, int(rr_steps))]
                with st.spinner("Running historical optimization..."):
                    rows = optimize_candles(candles, thresholds, rrs, int(top_n))
                    wf = walk_forward_candles(candles, thresholds, rrs, train_ratio=0.7, top_n=int(top_n))
                st.subheader("Best parameter sets")
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                st.subheader("Walk-forward validation")
                st.write(f"Train candles: {wf['train_candles']:,} · Test candles: {wf['test_candles']:,}")
                wf_rows = []
                for item in wf["candidates"]:
                    wf_rows.append({
                        **item["parameters"],
                        "train_score": round(item["train_score"], 6),
                        "test_score": round(item["test_score"], 6),
                        "test_return_pct": item["test"].get("return_pct", 0.0),
                        "test_drawdown_pct": item["test"].get("max_drawdown_pct", 0.0),
                        "test_profit_factor": item["test"].get("profit_factor", 0.0),
                    })
                st.dataframe(pd.DataFrame(wf_rows), use_container_width=True, hide_index=True)
                st.success("Optimization completed. Review out-of-sample results before promoting a candidate.")
