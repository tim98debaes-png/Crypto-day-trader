"""Read-only operational alerts for the simulation-only paper session.

The alert engine converts stable session/operations snapshots into a small,
deterministic contract suitable for a dashboard or notifier. It never mutates
portfolio state and never places exchange orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


SCHEMA_VERSION = 1
INFO = "INFO"
WARNING = "WARNING"
CRITICAL = "CRITICAL"
_SEVERITY_ORDER = {INFO: 0, WARNING: 1, CRITICAL: 2}


@dataclass(frozen=True)
class AlertThresholds:
    """Safety thresholds for operational paper-session alerts."""

    daily_loss_warning_pct: float = 2.0
    daily_loss_critical_pct: float = 3.0
    stale_minutes_warning: float = 5.0
    stale_minutes_critical: float = 15.0

    def __post_init__(self):
        if self.daily_loss_warning_pct <= 0:
            raise ValueError("daily_loss_warning_pct must be positive")
        if self.daily_loss_critical_pct < self.daily_loss_warning_pct:
            raise ValueError("daily_loss_critical_pct must be >= warning threshold")
        if self.stale_minutes_warning <= 0:
            raise ValueError("stale_minutes_warning must be positive")
        if self.stale_minutes_critical < self.stale_minutes_warning:
            raise ValueError("stale_minutes_critical must be >= warning threshold")


def _alert(code: str, severity: str, message: str, **details: Any) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "code": code,
        "severity": severity,
        "message": message,
        "details": details,
    }


def build_alerts(
    session_status: dict[str, Any],
    operations_status: dict[str, Any] | None = None,
    thresholds: AlertThresholds | None = None,
) -> list[dict]:
    """Return deterministic alerts from read-only status snapshots."""
    thresholds = thresholds or AlertThresholds()
    operations_status = operations_status or {}
    alerts: list[dict] = []

    state = str(session_status.get("state", "UNKNOWN")).upper()
    if state == "STOPPED":
        alerts.append(_alert("SESSION_STOPPED", CRITICAL, "Paper session is stopped."))
    elif state == "PAUSED":
        alerts.append(_alert("SESSION_PAUSED", WARNING, "Paper session is paused."))
    elif state == "UNKNOWN":
        alerts.append(_alert("SESSION_STATE_UNKNOWN", CRITICAL, "Paper session state is unknown."))

    stale = operations_status.get("minutes_since_last_event")
    if stale is not None:
        try:
            stale = float(stale)
        except (TypeError, ValueError):
            stale = None
    if stale is not None:
        if stale >= thresholds.stale_minutes_critical:
            alerts.append(
                _alert(
                    "SESSION_STALE_CRITICAL",
                    CRITICAL,
                    "No paper-session event has been observed within the critical stale window.",
                    minutes=stale,
                    threshold_minutes=thresholds.stale_minutes_critical,
                )
            )
        elif stale >= thresholds.stale_minutes_warning:
            alerts.append(
                _alert(
                    "SESSION_STALE_WARNING",
                    WARNING,
                    "Paper-session activity is becoming stale.",
                    minutes=stale,
                    threshold_minutes=thresholds.stale_minutes_warning,
                )
            )

    risk_rows: Iterable[dict] = operations_status.get("daily_risk") or []
    for row in risk_rows:
        try:
            loss = abs(float(row.get("daily_loss_pct", 0.0)))
        except (TypeError, ValueError):
            continue
        symbol = str(row.get("symbol", "UNKNOWN"))
        if row.get("blocked") or loss >= thresholds.daily_loss_critical_pct:
            alerts.append(
                _alert(
                    "DAILY_LOSS_CRITICAL",
                    CRITICAL,
                    f"Daily loss limit is critical for {symbol}.",
                    symbol=symbol,
                    daily_loss_pct=row.get("daily_loss_pct"),
                    threshold_pct=thresholds.daily_loss_critical_pct,
                )
            )
        elif loss >= thresholds.daily_loss_warning_pct:
            alerts.append(
                _alert(
                    "DAILY_LOSS_WARNING",
                    WARNING,
                    f"Daily loss is approaching the limit for {symbol}.",
                    symbol=symbol,
                    daily_loss_pct=row.get("daily_loss_pct"),
                    threshold_pct=thresholds.daily_loss_warning_pct,
                )
            )

    health = str(operations_status.get("health", "")).upper()
    if health == "BLOCKED" and not any(a["code"] == "DAILY_LOSS_CRITICAL" for a in alerts):
        alerts.append(_alert("OPERATIONS_BLOCKED", CRITICAL, "Paper operations are blocked."))
    elif health == "WATCH" and not any(a["severity"] == CRITICAL for a in alerts):
        alerts.append(_alert("OPERATIONS_WATCH", WARNING, "Paper operations require attention."))

    unique: dict[tuple[str, str], dict] = {}
    for item in alerts:
        unique[(item["code"], str(item["details"].get("symbol", "")))] = item

    return sorted(
        unique.values(),
        key=lambda item: (-_SEVERITY_ORDER[item["severity"]], item["code"], str(item["details"])),
    )
