"""Phase 29 operational helpers: structured audit events and safe shutdown."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json

@dataclass(frozen=True)
class AuditEvent:
    event: str
    client_order_id: str | None = None
    state: str | None = None
    reason: str | None = None
    timestamp: str = ""

    def to_json(self) -> str:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp or datetime.now(timezone.utc).isoformat()
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

def shutdown_state(open_order_count: int, reconciliation_complete: bool) -> str:
    if open_order_count < 0:
        raise ValueError("open_order_count")
    if open_order_count and not reconciliation_complete:
        return "BLOCKED_RECONCILIATION_REQUIRED"
    return "SAFE_TO_STOP"
