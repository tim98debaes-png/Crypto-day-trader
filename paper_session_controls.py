"""Lifecycle controls for simulation-only paper sessions.

This module deliberately has no exchange or order-routing integration.
It provides a tiny state machine that lets the UI/operator pause, resume,
and stop a paper session without changing trading semantics.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


RUNNING = "RUNNING"
PAUSED = "PAUSED"
STOPPED = "STOPPED"


@dataclass
class PaperSessionControl:
    """Explicit lifecycle state for a paper session."""

    state: str = RUNNING
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self):
        if self.state not in {RUNNING, PAUSED, STOPPED}:
            raise ValueError(f"invalid paper session state: {self.state}")

    def _set(self, state: str) -> str:
        self.state = state
        self.updated_at = datetime.now(timezone.utc).isoformat()
        return self.state

    def start(self) -> str:
        return self._set(RUNNING)

    def resume(self) -> str:
        return self._set(RUNNING)

    def pause(self) -> str:
        return self._set(PAUSED)

    def stop(self) -> str:
        return self._set(STOPPED)

    @property
    def can_tick(self) -> bool:
        return self.state == RUNNING

    def snapshot(self) -> dict:
        return {
            "schema_version": 1,
            "simulation_only": True,
            "state": self.state,
            "can_tick": self.can_tick,
            "updated_at": self.updated_at,
        }
