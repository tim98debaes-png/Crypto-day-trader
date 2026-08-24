import pytest

from paper_alerts import (
    CRITICAL,
    WARNING,
    AlertThresholds,
    build_alerts,
)


def running_session():
    return {
        "schema_version": 1,
        "simulation_only": True,
        "state": "RUNNING",
        "can_tick": True,
    }


def test_paused_session_emits_warning():
    alerts = build_alerts({**running_session(), "state": "PAUSED"})
    assert alerts[0]["code"] == "SESSION_PAUSED"
    assert alerts[0]["severity"] == WARNING


def test_stopped_session_is_critical():
    alerts = build_alerts({**running_session(), "state": "STOPPED"})
    assert alerts[0]["code"] == "SESSION_STOPPED"
    assert alerts[0]["severity"] == CRITICAL


def test_daily_loss_warning_and_critical_thresholds():
    operations = {
        "health": "HEALTHY",
        "daily_risk": [
            {"symbol": "BTCUSDT", "daily_loss_pct": -2.2, "blocked": False},
            {"symbol": "ETHUSDT", "daily_loss_pct": -3.0, "blocked": True},
        ],
    }
    alerts = build_alerts(running_session(), operations)

    codes = {(alert["code"], alert["details"]["symbol"]) for alert in alerts}
    assert ("DAILY_LOSS_WARNING", "BTCUSDT") in codes
    assert ("DAILY_LOSS_CRITICAL", "ETHUSDT") in codes


def test_stale_activity_uses_configured_thresholds():
    thresholds = AlertThresholds(stale_minutes_warning=3, stale_minutes_critical=10)
    operations = {"health": "HEALTHY", "minutes_since_last_event": 11}

    alerts = build_alerts(running_session(), operations, thresholds)

    assert alerts[0]["code"] == "SESSION_STALE_CRITICAL"
    assert alerts[0]["severity"] == CRITICAL


def test_alerts_are_deduplicated_and_deterministically_sorted():
    operations = {
        "health": "WATCH",
        "minutes_since_last_event": 6,
        "daily_risk": [
            {"symbol": "BTCUSDT", "daily_loss_pct": -2.1, "blocked": False},
            {"symbol": "BTCUSDT", "daily_loss_pct": -2.1, "blocked": False},
        ],
    }
    first = build_alerts(running_session(), operations)
    second = build_alerts(running_session(), operations)

    assert first == second
    assert sum(alert["code"] == "DAILY_LOSS_WARNING" for alert in first) == 1


def test_invalid_thresholds_are_rejected():
    with pytest.raises(ValueError):
        AlertThresholds(daily_loss_warning_pct=4, daily_loss_critical_pct=3)
    with pytest.raises(ValueError):
        AlertThresholds(stale_minutes_warning=10, stale_minutes_critical=5)
