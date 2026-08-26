"""Phase 32 Streamlit presentation-layer contracts."""

from phase32_dashboard import build_snapshot
from phase32_streamlit_dashboard import dashboard_payload, render_dashboard


class FakeStreamlit:
    def __init__(self):
        self.calls = []

    def subheader(self, value):
        self.calls.append(("subheader", value))

    def metric(self, label, value):
        self.calls.append(("metric", label, value))

    def caption(self, value):
        self.calls.append(("caption", value))

    def warning(self, value):
        self.calls.append(("warning", value))


def test_phase32_dashboard_payload_matches_snapshot():
    snapshot = build_snapshot(
        active_candidate={"id": "candidate-1", "status": "ACTIVE"},
        open_positions=1,
        equity=1010,
        drawdown_pct=-1,
        allow_new_entries=True,
        heartbeat_age_seconds=20,
    )
    assert dashboard_payload(snapshot) == snapshot.as_dict()


def test_phase32_renderer_is_read_only_and_surfaces_degraded_alerts():
    snapshot = build_snapshot(
        active_candidate=None,
        open_positions=0,
        equity=800,
        drawdown_pct=-25,
        allow_new_entries=False,
        heartbeat_age_seconds=400,
    )
    fake = FakeStreamlit()
    render_dashboard(fake, snapshot)
    assert ("metric", "New entries", "BLOCKED") in fake.calls
    warnings = [value for kind, value in fake.calls if kind == "warning"]
    assert "stale_heartbeat" in warnings
    assert "drawdown_limit" in warnings
    assert "no_active_candidate" in warnings
