"""Persistent registry for approved optimizer candidates and controlled rollouts.

The registry is deliberately small and file-backed so paper-trading state remains
portable and auditable. It never places orders and never promotes a candidate
without an explicit promotion decision.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from candidate_promotion import PromotionDecision, promote_candidate


class CandidateRegistry:
    """Store candidate versions, approvals, active rollout and rollback history."""

    def __init__(self, path: str | os.PathLike[str] = "data/candidate_registry.json"):
        self.path = Path(path)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "candidates": {}, "active_id": None, "events": []}
        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("candidate registry must contain an object")
        data.setdefault("version", 1)
        data.setdefault("candidates", {})
        data.setdefault("active_id", None)
        data.setdefault("events", [])
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix="candidate-registry-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    @staticmethod
    def candidate_id(candidate: dict[str, Any]) -> str:
        payload = json.dumps(candidate, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def register(self, candidate: dict[str, Any]) -> str:
        if not isinstance(candidate, dict) or not candidate:
            raise ValueError("candidate must be a non-empty object")
        data = self._load()
        candidate_id = self.candidate_id(candidate)
        if candidate_id not in data["candidates"]:
            data["candidates"][candidate_id] = {
                "id": candidate_id,
                "candidate": dict(candidate),
                "status": "REGISTERED",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "promoted_at": None,
            }
            data["events"].append({
                "event": "REGISTERED",
                "candidate_id": candidate_id,
                "at": datetime.now(timezone.utc).isoformat(),
            })
            self._save(data)
        return candidate_id

    def get(self, candidate_id: str) -> dict[str, Any] | None:
        return self._load()["candidates"].get(candidate_id)

    def active(self) -> dict[str, Any] | None:
        data = self._load()
        active_id = data.get("active_id")
        return data["candidates"].get(active_id) if active_id else None

    def promote(self, candidate_id: str, human_approved: bool = False) -> PromotionDecision:
        data = self._load()
        entry = data["candidates"].get(candidate_id)
        if entry is None:
            return PromotionDecision("BLOCKED", "unknown_candidate", {})

        decision = promote_candidate(entry["candidate"], human_approved=human_approved)
        if not decision.approved:
            data["events"].append({
                "event": "BLOCKED",
                "candidate_id": candidate_id,
                "reason": decision.reason,
                "at": datetime.now(timezone.utc).isoformat(),
            })
            self._save(data)
            return decision

        previous_id = data.get("active_id")
        if previous_id and previous_id != candidate_id:
            data["candidates"][previous_id]["status"] = "ROLLED_BACK"
        entry["status"] = "ACTIVE"
        entry["promoted_at"] = decision.promoted_at
        data["active_id"] = candidate_id
        data["events"].append({
            "event": "PROMOTED",
            "candidate_id": candidate_id,
            "previous_id": previous_id,
            "at": decision.promoted_at,
        })
        self._save(data)
        return decision

    def rollback(self, candidate_id: str | None = None) -> str | None:
        """Deactivate the current candidate and optionally restore a prior candidate."""
        data = self._load()
        current_id = data.get("active_id")
        if current_id:
            data["candidates"][current_id]["status"] = "ROLLED_BACK"

        target_id = candidate_id
        if target_id is None:
            promoted = [
                entry for entry in data["candidates"].values()
                if entry.get("status") == "ROLLED_BACK"
            ]
            promoted.sort(key=lambda entry: entry.get("promoted_at") or "", reverse=True)
            target_id = promoted[0]["id"] if promoted else None

        if target_id is not None:
            target = data["candidates"].get(target_id)
            if target is None:
                raise KeyError(f"unknown candidate: {target_id}")
            target["status"] = "ACTIVE"

        data["active_id"] = target_id
        data["events"].append({
            "event": "ROLLBACK",
            "from_id": current_id,
            "to_id": target_id,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        self._save(data)
        return target_id

    def history(self) -> list[dict[str, Any]]:
        return list(self._load()["events"])
