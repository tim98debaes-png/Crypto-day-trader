from pathlib import Path

from live_paper_session import LivePaperSession
from paper_session_controls import PAUSED, RUNNING, STOPPED, PaperSessionControl
from paper_session_state import default_path, load, load_control, save, save_control


def test_session_state_round_trip(tmp_path: Path):
    config = {"symbols": ["BTCUSDT", "ETHUSDT"], "interval_seconds": 5}
    path = default_path(config, str(tmp_path))
    control = PaperSessionControl()
    control.pause()

    save_control(path, config, control)
    restored = load_control(path, config)

    assert restored is not None
    assert restored.state == PAUSED
    assert restored.updated_at == control.updated_at


def test_session_state_isolated_by_config(tmp_path: Path):
    config = {"symbols": ["BTCUSDT"], "interval_seconds": 5}
    other_config = {"symbols": ["ETHUSDT"], "interval_seconds": 5}
    path = default_path(config, str(tmp_path))

    save(path, config, PaperSessionControl(state=STOPPED).snapshot())

    assert load(path, config)["state"] == STOPPED
    assert load(path, other_config) is None


def test_corrupt_or_invalid_state_is_ignored(tmp_path: Path):
    config = {"symbols": ["BTCUSDT"], "interval_seconds": 5}
    path = default_path(config, str(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"schema_version": 1, "config": {}}', encoding="utf-8")

    assert load(path, config) is None


def test_live_session_restores_stopped_state(tmp_path: Path):
    first = LivePaperSession(
        ["BTCUSDT"], interval_seconds=5, persist_state=True, state_dir=str(tmp_path)
    )
    assert first.state == RUNNING
    first.stop()

    second = LivePaperSession(
        ["BTCUSDT"], interval_seconds=5, persist_state=True, state_dir=str(tmp_path)
    )

    assert second.state == STOPPED
    assert second.status()["simulation_only"] is True


def test_live_session_resume_persists(tmp_path: Path):
    session = LivePaperSession(
        ["BTCUSDT"], interval_seconds=5, persist_state=True, state_dir=str(tmp_path)
    )
    session.pause()
    assert session.state == PAUSED

    restored = LivePaperSession(
        ["BTCUSDT"], interval_seconds=5, persist_state=True, state_dir=str(tmp_path)
    )
    assert restored.state == PAUSED

    restored.resume()
    resumed = LivePaperSession(
        ["BTCUSDT"], interval_seconds=5, persist_state=True, state_dir=str(tmp_path)
    )
    assert resumed.state == RUNNING
