"""Resilient supervisor for long-running simulation-only paper sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional


@dataclass
class RuntimeCheckpoint:
    ticks: int = 0
    last_tick_at: Optional[str] = None
    last_error: Optional[str] = None
    consecutive_errors: int = 0
    started_at: Optional[str] = None

    def snapshot(self) -> dict:
        return {
            "schema_version": 1,
            "ticks": self.ticks,
            "last_tick_at": self.last_tick_at,
            "last_error": self.last_error,
            "consecutive_errors": self.consecutive_errors,
            "started_at": self.started_at,
        }


@dataclass
class PaperRuntime:
    tick_fn: Callable[[], object]
    checkpoint_fn: Optional[Callable[[dict], None]] = None
    checkpoint_every: int = 10
    max_consecutive_errors: int = 3
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    checkpoint: RuntimeCheckpoint = field(default_factory=RuntimeCheckpoint)

    def __post_init__(self):
        if self.checkpoint_every < 1:
            raise ValueError("checkpoint_every must be >= 1")
        if self.max_consecutive_errors < 1:
            raise ValueError("max_consecutive_errors must be >= 1")

    def _now(self) -> str:
        value = self.clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    def _checkpoint(self) -> None:
        if self.checkpoint_fn is not None:
            self.checkpoint_fn(self.checkpoint.snapshot())

    def run_once(self) -> object:
        if self.checkpoint.started_at is None:
            self.checkpoint.started_at = self._now()
        try:
            result = self.tick_fn()
        except Exception as exc:
            self.checkpoint.consecutive_errors += 1
            self.checkpoint.last_error = f"{type(exc).__name__}: {exc}"
            self.checkpoint.last_tick_at = self._now()
            self._checkpoint()
            if self.checkpoint.consecutive_errors >= self.max_consecutive_errors:
                raise RuntimeError("paper runtime stopped after consecutive tick errors") from exc
            return None

        self.checkpoint.ticks += 1
        self.checkpoint.last_tick_at = self._now()
        self.checkpoint.last_error = None
        self.checkpoint.consecutive_errors = 0
        if self.checkpoint.ticks % self.checkpoint_every == 0:
            self._checkpoint()
        return result

    def run(self, max_ticks: Optional[int] = None) -> int:
        completed = 0
        while max_ticks is None or completed < max_ticks:
            self.run_once()
            completed += 1
        self._checkpoint()
        return completed
