from candidate_dashboard_view import build_session_dashboard
from paper_session_observability import PaperSessionObserver


def test_session_dashboard_exposes_health_and_history(tmp_path):
    observer = PaperSessionObserver(state_path=str(tmp_path / "obs.json"))
    observer.heartbeat(
        {
            "equity": 1000.0,
            "closed_trades": 0,
            "profit_factor": 0.0,
            "return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "open_positions": 0,
            "monitor_status": "HEALTHY",
        },
        active_candidate_id="candidate-1",
        timestamp="2026-08-25T19:00:00+00:00",
    )

    view = build_session_dashboard(observer)

    # The checkpoint is intentionally old relative to the test runner clock;
    # the dashboard must expose the real operational state rather than masking
    # a stale session as healthy.
    assert view["health"]["status"] == "STALE"
    assert view["health"]["sequence"] == 1
    assert view["checkpoints"][0]["active_candidate_id"] == "candidate-1"
    assert view["source"] == "paper_session_observability"
