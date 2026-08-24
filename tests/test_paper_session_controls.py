from paper_session_controls import PAUSED, RUNNING, STOPPED, PaperSessionControl


def test_session_control_starts_running_and_reports_simulation_only():
    control = PaperSessionControl()
    status = control.snapshot()

    assert control.state == RUNNING
    assert status["state"] == RUNNING
    assert status["can_tick"] is True
    assert status["simulation_only"] is True


def test_session_control_pause_and_resume():
    control = PaperSessionControl()

    assert control.pause() == PAUSED
    assert control.can_tick is False
    assert control.resume() == RUNNING
    assert control.can_tick is True


def test_session_control_stop_blocks_ticks_until_started_again():
    control = PaperSessionControl()

    assert control.stop() == STOPPED
    assert control.can_tick is False
    assert control.start() == RUNNING
    assert control.can_tick is True


def test_session_control_rejects_unknown_state():
    try:
        PaperSessionControl(state="UNKNOWN")
    except ValueError as exc:
        assert "invalid paper session state" in str(exc)
    else:
        raise AssertionError("unknown session state must be rejected")
