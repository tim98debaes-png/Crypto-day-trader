from candidate_registry import CandidateRegistry
from paper_session_monitor import BLOCKED, HEALTHY, ROLLBACK, WATCH, PaperSessionMonitor


def valid_candidate(label="A"):
    return {
        "Status": "ROBUST",
        "label": label,
        "OOS %": 4.0,
        "OOS PF": 1.5,
        "OOS trades": 20,
        "OOS DD": -8.0,
        "Stability": 75,
        "MC P05 %": 2.0,
    }


def snapshot(**overrides):
    value = {
        "closed_trades": 20,
        "profit_factor": 1.35,
        "return_pct": 2.0,
        "max_drawdown_pct": 8.0,
        "consecutive_losses": 1,
    }
    value.update(overrides)
    return value


def setup_registry(tmp_path, two_candidates=True):
    registry = CandidateRegistry(tmp_path / "registry.json")
    first = registry.register(valid_candidate("A"))
    registry.promote(first, human_approved=True)
    second = None
    if two_candidates:
        second = registry.register(valid_candidate("B"))
        registry.promote(second, human_approved=True)
    return registry, first, second


def test_insufficient_sample_does_not_rollback(tmp_path):
    registry, first, second = setup_registry(tmp_path)
    monitor = PaperSessionMonitor(registry)

    decision = monitor.evaluate(second, snapshot(closed_trades=19, profit_factor=0.5, return_pct=-20.0))

    assert decision.status == HEALTHY
    assert decision.reason == "insufficient_sample"
    assert registry.active()["id"] == second


def test_single_soft_breach_is_watch_only(tmp_path):
    registry, first, second = setup_registry(tmp_path)
    monitor = PaperSessionMonitor(registry)

    decision = monitor.evaluate(second, snapshot(profit_factor=1.1))

    assert decision.status == WATCH
    assert decision.reason == "degradation_watch"
    assert registry.active()["id"] == second


def test_two_rollback_breaches_restore_safe_previous_candidate(tmp_path):
    registry, first, second = setup_registry(tmp_path)
    monitor = PaperSessionMonitor(registry)

    decision = monitor.evaluate(
        second,
        snapshot(profit_factor=0.8, return_pct=-7.0),
    )

    assert decision.status == ROLLBACK
    assert decision.target_id == first
    assert decision.allow_new_entries is True
    assert registry.active()["id"] == first
    assert registry.get(second)["status"] == "ROLLED_BACK"

    monitor_events = [event for event in registry.history() if event["event"] == "MONITOR_DECISION"]
    assert monitor_events[-1]["reason"] == "safe_fallback_restored"
    assert "profit_factor" in monitor_events[-1]["breaches"]
    assert "return" in monitor_events[-1]["breaches"]


def test_severe_drawdown_rolls_back_with_one_hard_breach(tmp_path):
    registry, first, second = setup_registry(tmp_path)
    monitor = PaperSessionMonitor(registry)

    decision = monitor.evaluate(second, snapshot(max_drawdown_pct=20.0))

    assert decision.status == ROLLBACK
    assert registry.active()["id"] == first


def test_no_safe_fallback_deactivates_and_fails_closed(tmp_path):
    registry, first, second = setup_registry(tmp_path, two_candidates=False)
    monitor = PaperSessionMonitor(registry)

    decision = monitor.evaluate(first, snapshot(profit_factor=0.7, return_pct=-8.0))

    assert decision.status == BLOCKED
    assert decision.reason == "no_safe_fallback"
    assert decision.allow_new_entries is False
    assert registry.active() is None
    assert registry.get(first)["status"] == "ROLLED_BACK"


def test_invalid_metrics_fail_closed_without_registry_switch(tmp_path):
    registry, first, second = setup_registry(tmp_path)
    monitor = PaperSessionMonitor(registry)

    decision = monitor.evaluate(second, {"closed_trades": 20, "profit_factor": "not-a-number"})

    assert decision.status == BLOCKED
    assert decision.reason == "invalid_metrics"
    assert decision.allow_new_entries is False
    assert registry.active()["id"] == second


def test_active_candidate_mismatch_fails_closed(tmp_path):
    registry, first, second = setup_registry(tmp_path)
    monitor = PaperSessionMonitor(registry)

    decision = monitor.evaluate(first, snapshot())

    assert decision.status == BLOCKED
    assert decision.reason == "active_candidate_changed"
    assert decision.allow_new_entries is False
    assert registry.active()["id"] == second


def test_deactivation_does_not_auto_restore_the_same_candidate(tmp_path):
    registry, first, second = setup_registry(tmp_path, two_candidates=False)

    removed = registry.deactivate()

    assert removed == first
    assert registry.active() is None
    assert registry.get(first)["status"] == "ROLLED_BACK"
