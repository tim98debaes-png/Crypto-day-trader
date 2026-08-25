"""Phase 22 sustained paper-session observability."""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from paper_state import load, save

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


def _safe_number(value: Any, *, infinity_cap: float = 1_000_000.0) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    if math.isinf(number):
        return infinity_cap if number > 0 else None
    return number


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
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]


def build_checkpoint(summary: dict[str, Any], *, sequence: int, active_candidate_id: Optional[str], timestamp: Optional[str] = None) -> SessionCheckpoint:
    required = ("equity", "closed_trades", "profit_factor", "return_pct", "max_drawdown_pct", "open_positions")
    if any(key not in summary for key in required):
        raise ValueError("paper summary is missing required observability fields")
    values = {key: _safe_number(summary[key]) for key in required}
    if any(value is None for value in values.values()):
        raise ValueError("paper summary contains invalid observability values")
    if int(sequence) < 1:
        raise ValueError("sequence must be positive")
    if values["closed_trades"] < 0 or values["max_drawdown_pct"] < 0 or values["open_positions"] < 0:
        raise ValueError("paper summary contains negative state values")
    body = {
        "timestamp": timestamp or _now(),
        "sequence": int(sequence),
        "equity": float(values["equity"]),
        "closed_trades": int(values["closed_trades"]),
        "profit_factor": float(values["profit_factor"]),
        "return_pct": float(values["return_pct"]),
        "max_drawdown_pct": float(values["max_drawdown_pct"]),
        "open_positions": int(values["open_positions"]),
        "monitor_status": str(summary.get("monitor_status") or "UNKNOWN"),
        "active_candidate_id": active_candidate_id,
        "schema_version": SCHEMA_VERSION,
    }
    return SessionCheckpoint(**body, state_hash=checkpoint_hash(body))


class PaperSessionObserver:
    """Append-only observer with durable checkpoints and stale-session checks."""

    def __init__(self, stale_after_seconds: int = 900, max_checkpoints: int = 10000, state_path: Optional[str] = None):
        if stale_after_seconds < 1:
            raise ValueError("stale_after_seconds must be positive")
        if max_checkpoints < 2:
            raise ValueError("max_checkpoints must be at least 2")
        self.stale_after_seconds = int(stale_after_seconds)
        self.max_checkpoints = int(max_checkpoints)
        self.state_path = Path(state_path or os.getenv("PAPER_OBSERVABILITY_PATH", ".paper_state/session_observability.json"))
        self._checkpoints: list[SessionCheckpoint] = []
        self._sequence = 0
        self._restore()

    @property
    def checkpoints(self) -> list[SessionCheckpoint]:
        return list(self._checkpoints)

    def _config(self) -> dict[str, Any]:
        return {"kind": "phase22_observability", "stale_after_seconds": self.stale_after_seconds}

    def _save(self) -> None:
        try:
            save(str(self.state_path), self._config(), {"checkpoints": self.export()})
        except OSError:
            pass

    def _restore(self) -> bool:
        state = load(str(self.state_path), self._config())
        if not state:
            return False
        try:
            restored = [SessionCheckpoint(**raw) for raw in state.get("checkpoints", []) if isinstance(raw, dict)]
            self._checkpoints = []
            self._sequence = 0
            for checkpoint in restored[-self.max_checkpoints:]:
                self.record(checkpoint, persist=False)
            return bool(self._checkpoints)
        except (KeyError, TypeError, ValueError):
            self._checkpoints = []
            self._sequence = 0
            return False

    def record(self, checkpoint: SessionCheckpoint, *, persist: bool = True) -> None:
        if checkpoint.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported checkpoint schema")
        body = asdict(checkpoint)
        expected_hash = body.pop("state_hash")
        if checkpoint_hash(body) != expected_hash:
            raise ValueError("checkpoint integrity hash mismatch")
        if checkpoint.sequence != self._sequence + 1:
            raise ValueError("checkpoint sequence gap")
        if self._checkpoints and _parse_time(checkpoint.timestamp) < _parse_time(self._checkpoints[-1].timestamp):
            raise ValueError("checkpoint timestamp moved backwards")
        self._checkpoints.append(checkpoint)
        self._checkpoints = self._checkpoints[-self.max_checkpoints:]
        self._sequence = checkpoint.sequence
        if persist:
            self._save()

    def heartbeat(self, summary: dict[str, Any], *, active_candidate_id: Optional[str], timestamp: Optional[str] = None) -> SessionCheckpoint:
        checkpoint = build_checkpoint(summary, sequence=self._sequence + 1, active_candidate_id=active_candidate_id, timestamp=timestamp)
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
            status, reason = STALE, "heartbeat_stale"
        elif latest.monitor_status in {"BLOCKED", "ROLLBACK"}:
            status, reason = DEGRADED, "paper_monitor_blocked" if latest.monitor_status == "BLOCKED" else "paper_monitor_rollback"
        else:
            status, reason = HEALTHY, "heartbeat_current"
        return {"status": status, "reason": reason, "age_seconds": round(age, 3), "checkpoints": len(self._checkpoints), "sequence": latest.sequence, "latest_timestamp": latest.timestamp, "active_candidate_id": latest.active_candidate_id, "monitor_status": latest.monitor_status, "equity": latest.equity, "closed_trades": latest.closed_trades, "profit_factor": latest.profit_factor, "return_pct": latest.return_pct, "max_drawdown_pct": latest.max_drawdown_pct, "open_positions": latest.open_positions}

    def export(self) -> list[dict[str, Any]]:
        return [asdict(checkpoint) for checkpoint in self._checkpoints]
