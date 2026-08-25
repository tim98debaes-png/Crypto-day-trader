"""Phase 22 sustained paper-session observability.

This module is read-only with respect to trading decisions. It records durable
session heartbeats/checkpoints, validates paper-session continuity, and exposes
an operational health summary. It never promotes candidates and never places
orders.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Optional

SCHEMA_VERSION = 1
HEALTHY = "HEALTHY"
DEGRADED = "DEGRADED"
STALE = "STALE"
INVALID = "INVALID"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class SessionCheckpoint:
    timestamp: str
    sequence: int
    equity: float
    closed_trades: int
    profit_factor: float
    return_pct: float
    max_drawdown_pct: float
    open_positions: int
    monitor_status: str
    active_candidate_id: Optional[str]
    state_hash: str
    schema_version: int = SCHEMA_VERSION


def checkpoint_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]


def build_checkpoint(
    summary: dict[str, Any],
    *,
    sequence: int,
    active_candidate_id: Optional[str],
    timestamp: Optional[str] = None,
) -> SessionCheckpoint:
    """Create a deterministic checkpoint from the current paper summary."""
    required = (
        "equity",
        "closed_trades",
        "profit_factor",
        "return_pct",
        "max_drawdown_pct",
        "open_positions",
    )
    if any(key not in summary for key in required):
        raise ValueError("paper summary is missing required observability fields")
    numeric = {key: summary[key] for key in required}
    if not all(_finite(value) for value in numeric.values()):
        raise ValueError("paper summary contains non-finite observability values")
    if int(sequence) < 1:
        raise ValueError("sequence must be positive")
    body = {
        "timestamp": timestamp or _now(),
        "sequence": int(sequence),
        **{key: float(value) if key not in {"closed_trades", "open_positions"} else int(value) for key, value in numeric.items()},
        "monitor_status": str(summary.get("monitor_status") or "UNKNOWN"),
        "active_candidate_id": active_candidate_id,
        "schema_version": SCHEMA_VERSION,
    }
    return SessionCheckpoint(**body, state_hash=checkpoint_hash(body))


class PaperSessionObserver:
    """Append-only in-memory observer with explicit validation and stale checks."""

    def __init__(self, stale_after_seconds: int = 900, max_checkpoints: int = 10000):
        if stale_after_seconds < 1:
            raise ValueError("stale_after_seconds must be positive")
        if max_checkpoints < 2:
            raise ValueError("max_checkpoints must be at least 2")
        self.stale_after_seconds = int(stale_after_seconds)
        self.max_checkpoints = int(max_checkpoints)
        self._checkpoints: list[SessionCheckpoint] = []
        self._sequence = 0

    @property
    def checkpoints(self) -> list[SessionCheckpoint]:
        return list(self._checkpoints)

    def record(self, checkpoint: SessionCheckpoint) -> None:
        """Record a checkpoint and reject broken sequence/hash continuity."""
        if checkpoint.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported checkpoint schema")
        if checkpoint.sequence != self._sequence + 1:
            raise ValueError("checkpoint sequence gap")
        body = asdict(checkpoint)
        expected_hash = body.pop("state_hash")
        if checkpoint_hash(body) != expected_hash:
            raise ValueError("checkpoint integrity hash mismatch")
        if self._checkpoints:
            previous = self._checkpoints[-1]
            if _parse_time(checkpoint.timestamp) < _parse_time(previous.timestamp):
                raise ValueError("checkpoint timestamp moved backwards")
        self._checkpoints.append(checkpoint)
        self._checkpoints = self._checkpoints[-self.max_checkpoints :]
        self._sequence = checkpoint.sequence

    def heartbeat(self, summary: dict[str, Any], *, active_candidate_id: Optional[str], timestamp: Optional[str] = None) -> SessionCheckpoint:
        checkpoint = build_checkpoint(
            summary,
            sequence=self._sequence + 1,
            active_candidate_id=active_candidate_id,
            timestamp=timestamp,
        )
        self.record(checkpoint)
        return checkpoint

    def health(self, now: Optional[str] = None) -> dict[str, Any]:
        if not self._checkpoints:
            return {"status": INVALID, "reason": "no_checkpoint", "age_seconds": None, "checkpoints": 0}
        latest = self._checkpoints[-1]
        try:
            age = max(0.0, (_parse_time(now or _now()) - _parse_time(latest.timestamp)).total_seconds())
        except (TypeError, ValueError):
            return {"status": INVALID, "reason": "invalid_now", "age_seconds": None, "checkpoints": len(self._checkpoints)}
        if age > self.stale_after_seconds:
            status = STALE
            reason = "heartbeat_stale"
        elif latest.monitor_status == "BLOCKED":
            status = DEGRADED
            reason = "paper_monitor_blocked"
        else:
            status = HEALTHY
            reason = "heartbeat_current"
        return {
            "status": status,
            "reason": reason,
            "age_seconds": round(age, 3),
            "checkpoints": len(self._checkpoints),
            "sequence": latest.sequence,
            "latest_timestamp": latest.timestamp,
            "active_candidate_id": latest.active_candidate_id,
            "monitor_status": latest.monitor_status,
            "equity": latest.equity,
            "closed_trades": latest.closed_trades,
            "profit_factor": latest.profit_factor,
            "return_pct": latest.return_pct,
            "max_drawdown_pct": latest.max_drawdown_pct,
            "open_positions": latest.open_positions,
        }

    def export(self) -> list[dict[str, Any]]:
        return [asdict(checkpoint) for checkpoint in self._checkpoints]
