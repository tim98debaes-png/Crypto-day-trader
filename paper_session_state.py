"""Durable persistence for the simulation-only paper session lifecycle.

The portfolio state already survives process restarts. Phase 11 extends that
same safety model to the RUNNING/PAUSED/STOPPED operator state so a restart
cannot accidentally turn a deliberately paused or stopped paper session back
on. The store contains no exchange credentials and is atomic on disk.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Optional

from paper_session_controls import PaperSessionControl, PAUSED, RUNNING, STOPPED


SCHEMA_VERSION = 1
DEFAULT_DIR = ".paper_state"
VALID_STATES = {RUNNING, PAUSED, STOPPED}


def fingerprint(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def default_path(config: dict[str, Any], base_dir: Optional[str] = None) -> Path:
    root = Path(base_dir or os.getenv("PAPER_STATE_DIR", DEFAULT_DIR))
    return root / f"session_{fingerprint(config)}.json"


def load(path: str | Path, expected_config: dict[str, Any]) -> Optional[dict[str, Any]]:
    file_path = Path(path)
    if not file_path.exists():
        return None
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload.get("schema_version") != SCHEMA_VERSION:
            return None
        if payload.get("config") != expected_config:
            return None
        state = payload.get("state")
        if not isinstance(state, dict) or state.get("state") not in VALID_STATES:
            return None
        return state
    except (OSError, ValueError, TypeError):
        return None


def save(path: str | Path, config: dict[str, Any], state: dict[str, Any]) -> None:
    if state.get("state") not in VALID_STATES:
        raise ValueError("invalid paper session state")

    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "config": config,
        "state": state,
    }
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=file_path.parent,
        prefix=file_path.name + ".",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
        temp_path = Path(handle.name)
    try:
        os.replace(temp_path, file_path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def load_control(
    path: str | Path, expected_config: dict[str, Any]
) -> Optional[PaperSessionControl]:
    state = load(path, expected_config)
    if state is None:
        return None
    control = PaperSessionControl(state=state["state"])
    if isinstance(state.get("updated_at"), str):
        control.updated_at = state["updated_at"]
    return control


def save_control(
    path: str | Path, config: dict[str, Any], control: PaperSessionControl
) -> None:
    save(path, config, control.snapshot())
