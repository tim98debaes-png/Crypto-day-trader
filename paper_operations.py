"""Operational status helpers for the simulation-only paper engine.

Read-only helpers: they never place orders and never mutate portfolio state.
They expose a small stable contract for session health, daily risk, event flow,
and paper-session identity so monitoring can be built without coupling the UI
to the execution internals.
"""

from datetime import datetime, timezone
import hashlib
import json


SCHEMA_VERSION = 1


def _iso_now():
    return datetime.now(timezone.utc)


def _parse_timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def session_identity(portfolio):
    """Return a stable identifier for the configured paper session."""
    config = getattr(portfolio, "_config", {})
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"paper-{digest}"


def _daily_risk(portfolio, marks):
    values = []
    for symbol, account in portfolio.accounts.items():
        mark = marks.get(symbol)
        values.append(
            {
                "symbol": symbol,
                "daily_loss_pct": round(account.daily_loss_pct(mark), 6),
                "limit_pct": float(account.max_daily_loss_pct),
                "blocked": not account.can_open(mark or 0.0) if account.position is None and mark else False,
            }
        )
    return values


def build_operations_status(portfolio, marks=None, now=None):
    """Build a read-only operational health snapshot."""
    marks = marks or {}
    now = now or _iso_now()
    events = portfolio.audit_log()
    closes = [event for event in events if event.get("event") == "CLOSE"]
    opens = [event for event in events if event.get("event") == "OPEN"]
    risk = _daily_risk(portfolio, marks)

    last_event = None
    event_times = [_parse_timestamp(event.get("timestamp")) for event in events]
    event_times = [value for value in event_times if value is not None]
    if event_times:
        last_event = max(event_times)

    stale_minutes = None
    if last_event is not None:
        stale_minutes = max(0.0, (now - last_event).total_seconds() / 60.0)

    persistence_enabled = bool(getattr(portfolio, "persist", False))
    has_accounts = bool(portfolio.accounts)
    blocked_accounts = sum(item["blocked"] for item in risk)

    if blocked_accounts:
        health = "BLOCKED"
    elif not persistence_enabled:
        health = "WATCH"
    else:
        health = "HEALTHY"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "simulation_only": True,
        "health": health,
        "session_id": session_identity(portfolio),
        "persistence_enabled": persistence_enabled,
        "state_path": getattr(portfolio, "state_path", None),
        "accounts": len(portfolio.accounts),
        "configured_symbols": len(getattr(portfolio, "coins", [])),
        "open_positions": sum(account.position is not None for account in portfolio.accounts.values()),
        "open_events": len(opens),
        "closed_events": len(closes),
        "total_events": len(events),
        "last_event_at": last_event.isoformat() if last_event else None,
        "minutes_since_last_event": round(stale_minutes, 3) if stale_minutes is not None else None,
        "daily_risk": risk,
        "blocked_accounts": blocked_accounts,
        "has_accounts": has_accounts,
    }


def event_summary(portfolio):
    """Return compact event counts grouped by type, direction and symbol."""
    events = portfolio.audit_log()
    by_event = {}
    by_direction = {"LONG": 0, "SHORT": 0}
    by_symbol = {}
    for event in events:
        event_name = str(event.get("event", "UNKNOWN")).upper()
        by_event[event_name] = by_event.get(event_name, 0) + 1
        direction = str(event.get("direction", "")).upper()
        if direction in by_direction:
            by_direction[direction] += 1
        symbol = str(event.get("symbol", ""))
        if symbol:
            by_symbol[symbol] = by_symbol.get(symbol, 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "by_event": by_event,
        "by_direction": by_direction,
        "by_symbol": by_symbol,
    }
