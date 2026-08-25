"""Inject and maintain the Phase 5 paper-trading dashboard.

The dashboard uses public market data and validated optimizer candidates.
It never places live exchange orders.
"""

from pathlib import Path
from textwrap import dedent

APP = Path("app.py")
FOOTER_MARKER = "# ============================================================\n# Footer\n# ============================================================"
DASHBOARD_MARKER = "# ---------------- Phase 5 Paper Trading Dashboard ----------------"
SIGNAL_IMPORT = "from signal_engine import generate_signal\n"
EXECUTION_IMPORT = "from paper_execution import PaperExecutionLoop\n"
PORTFOLIO_IMPORT = "from paper_portfolio import PaperPortfolio\n"
FEED_IMPORT = "from market_feed import BinancePublicFeed\n"


def main():
    text = APP.read_text(encoding="utf-8")

    if SIGNAL_IMPORT not in text:
        raise SystemExit("signal_engine import marker not found")

    imports = SIGNAL_IMPORT
    for marker in (EXECUTION_IMPORT, PORTFOLIO_IMPORT, FEED_IMPORT):
        if marker not in text:
            text = text.replace(imports, imports + marker, 1)
            imports += marker

    if DASHBOARD_MARKER not in text:
        raise SystemExit("Phase 5 dashboard marker not found")

    start = text.index(DASHBOARD_MARKER)
    end = text.index(FOOTER_MARKER, start)
    block = text[start:end].strip()

    # The dashboard may already be committed in wrapped form. Normalize it
    # back to a top-level Streamlit block so the injector is idempotent and
    # cannot create an unexpected-unindent syntax error.
    if block.startswith("@st.fragment(run_every=\"5m\")"):
        function_marker = "def phase5_dashboard():\n"
        if function_marker not in block:
            raise SystemExit("Phase 5 dashboard function marker not found")
        body = block.split(function_marker, 1)[1]
        body = dedent(body)
        body = body.replace("\nphase5_dashboard()", "", 1).rstrip()
        block = body

    # If the dashboard is still the older top-level version, make execution
    # automatic within the current Streamlit run without changing indentation.
    old_button = '    run_cycle = st.button("▶️ Verwerk nieuwe gesloten candles", key="phase5_run_cycle")'
    new_button = (
        '    st.button("▶️ Verwerk nu", key="phase5_run_cycle")\n'
        '    run_cycle = True\n'
        '    st.caption("🟢 Auto-check actief — elke 5 minuten; alleen nieuwe gesloten candles worden verwerkt.")'
    )
    block = block.replace(old_button, new_button, 1)
    block = block.replace(
        'result = {"action": "PREVIEW", "reason": "druk op verwerk om paper execution te activeren"}',
        'result = {"action": "WAIT", "reason": "geen nieuwe gesloten candle of geen gevalideerde kandidaat"}',
        1,
    )

    text = text[:start] + block + "\n\n" + text[end:]
    APP.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
