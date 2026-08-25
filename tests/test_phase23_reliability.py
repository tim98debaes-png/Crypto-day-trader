from pathlib import Path

from paper_engine import PaperAccount
from paper_session_observability import PaperSessionObserver
from phase23_reliability import PaperReliabilityHarness


def markets(count=60):
    return [
        {"symbol": "BTCUSDT", "price": 100.0 + (i % 5), "timestamp": f"2026-08-25T10:{i:02d}:00+00:00"}
        for i in range(count)
    ]


def test_long_run_with_restart_recovers(tmp_path):
    harness = PaperReliabilityHarness(PaperAccount, str(tmp_path / "obs.json"))
    report = harness.run(markets(), restart_after=30)
    assert report.passed, report.to_dict()
    assert report.events == 60
    assert report.restarts == 1
    assert report.checkpoints == 60


def test_observability_state_survives_restart(tmp_path):
    path = tmp_path / "obs.json"
    observer = PaperSessionObserver(state_path=str(path))
    for i in range(1, 4):
        observer.heartbeat({
            "equity": 1000,
            "closed_trades": i,
            "profit_factor": 1.5,
            "return_pct": 0,
            "max_drawdown_pct": 0,
            "open_positions": 0,
            "monitor_status": "HEALTHY",
        }, active_candidate_id="candidate-1", timestamp=f"2026-08-25T10:0{i}:00+00:00")

    restored = PaperSessionObserver(state_path=str(path))
    assert restored.checkpoints[-1].sequence == 3
    assert restored.checkpoints[-1].active_candidate_id == "candidate-1"
    assert restored.health(now="2026-08-25T10:03:30+00:00")["status"] == "HEALTHY"


def test_corrupted_checkpoint_fails_closed(tmp_path):
    path = tmp_path / "obs.json"
    observer = PaperSessionObserver(state_path=str(path))
    observer.heartbeat({
        "equity": 1000,
        "closed_trades": 20,
        "profit_factor": 1.5,
        "return_pct": 2,
        "max_drawdown_pct": 4,
        "open_positions": 0,
        "monitor_status": "HEALTHY",
    }, active_candidate_id="candidate-1", timestamp="2026-08-25T10:00:00+00:00")

    raw = path.read_text()
    path.write_text(raw.replace('"equity": 1000.0', '"equity": 999.0'))
    restored = PaperSessionObserver(state_path=str(path))
    assert restored.health(now="2026-08-25T10:00:01+00:00")["status"] == "INVALID"


def test_stale_session_is_detected(tmp_path):
    observer = PaperSessionObserver(stale_after_seconds=60, state_path=str(tmp_path / "obs.json"))
    observer.heartbeat({
        "equity": 1000,
        "closed_trades": 20,
        "profit_factor": 1.5,
        "return_pct": 2,
        "max_drawdown_pct": 4,
        "open_positions": 0,
        "monitor_status": "HEALTHY",
    }, active_candidate_id="candidate-1", timestamp="2026-08-25T10:00:00+00:00")
    assert observer.health(now="2026-08-25T10:02:01+00:00")["status"] == "STALE"
