"""Atomic JSON persistence for the paper-trading engine.

The storage layer is deliberately exchange-agnostic and contains no secrets.
It is intended for Streamlit/session persistence and can later be swapped for
an external durable store without changing the paper engine API.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Optional


SCHEMA_VERSION = 1
DEFAULT_DIR = ".paper_state"


def fingerprint(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def default_path(config: dict[str, Any], base_dir: Optional[str] = None) -> Path:
    root = Path(base_dir or os.getenv("PAPER_STATE_DIR", DEFAULT_DIR))
    return root / f"portfolio_{fingerprint(config)}.json"


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
        return state if isinstance(state, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def save(path: str | Path, config: dict[str, Any], state: dict[str, Any]) -> None:
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
