"""Phase 31 persistent-state integrity and corruption safety tests."""

import json

from paper_state import SCHEMA_VERSION, fingerprint, load, save


def test_phase31_state_roundtrip_and_config_isolation(tmp_path):
    path = tmp_path / "state.json"
    config = {"capital": 1000.0, "risk_pct": 0.5, "coins": ["BTCUSDT"]}
    state = {"equity": 1012.5, "open": True}

    save(path, config, state)
    assert load(path, config) == state
    assert load(path, {**config, "risk_pct": 1.0}) is None
    assert fingerprint(config) != fingerprint({**config, "risk_pct": 1.0})


def test_phase31_corrupt_state_fails_closed(tmp_path):
    path = tmp_path / "state.json"
    config = {"capital": 1000.0}
    path.write_text("{not-json", encoding="utf-8")
    assert load(path, config) is None


def test_phase31_unsupported_schema_fails_closed(tmp_path):
    path = tmp_path / "state.json"
    config = {"capital": 1000.0}
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION + 1, "config": config, "state": {"open": True}}),
        encoding="utf-8",
    )
    assert load(path, config) is None


def test_phase31_wrong_state_shape_fails_closed(tmp_path):
    path = tmp_path / "state.json"
    config = {"capital": 1000.0}
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "config": config, "state": []}),
        encoding="utf-8",
    )
    assert load(path, config) is None
