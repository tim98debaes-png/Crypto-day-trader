from datetime import datetime, timezone

import pytest

from paper_runtime import PaperRuntime


class Clock:
    def __init__(self):
        self.value = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value


def test_runtime_checkpoints_on_interval_and_finally():
    calls = []
    ticks = []

    runtime = PaperRuntime(
        tick_fn=lambda: ticks.append(len(ticks) + 1),
        checkpoint_fn=lambda state: calls.append(state.copy()),
        checkpoint_every=2,
    )

    assert runtime.run(max_ticks=3) == 3
    assert [state["ticks"] for state in calls] == [2, 3]
    assert runtime.checkpoint.last_error is None


def test_runtime_recovers_from_transient_error():
    calls = []
    attempts = iter([RuntimeError("temporary"), "ok"])

    def tick():
        value = next(attempts)
        if isinstance(value, Exception):
            raise value
        return value

    runtime = PaperRuntime(
        tick_fn=tick,
        checkpoint_fn=lambda state: calls.append(state.copy()),
        max_consecutive_errors=2,
    )

    assert runtime.run_once() is None
    assert runtime.checkpoint.consecutive_errors == 1
    assert runtime.run_once() == "ok"
    assert runtime.checkpoint.consecutive_errors == 0
    assert runtime.checkpoint.last_error is None
    assert calls


def test_runtime_stops_after_consecutive_errors():
    runtime = PaperRuntime(tick_fn=lambda: (_ for _ in ()).throw(ValueError("bad")), max_consecutive_errors=2)

    assert runtime.run_once() is None
    with pytest.raises(RuntimeError, match="consecutive tick errors"):
        runtime.run_once()
    assert runtime.checkpoint.consecutive_errors == 2


def test_runtime_records_utc_timestamps():
    clock = Clock()
    runtime = PaperRuntime(tick_fn=lambda: "ok", clock=clock)

    runtime.run_once()

    assert runtime.checkpoint.started_at == "2026-08-25T12:00:00+00:00"
    assert runtime.checkpoint.last_tick_at == "2026-08-25T12:00:00+00:00"


def test_invalid_runtime_configuration_is_rejected():
    with pytest.raises(ValueError):
        PaperRuntime(tick_fn=lambda: None, checkpoint_every=0)
    with pytest.raises(ValueError):
        PaperRuntime(tick_fn=lambda: None, max_consecutive_errors=0)
