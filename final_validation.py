"""Phase 30 final deterministic go/no-go validation."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class GoNoGo:
    go: bool
    checks: dict[str, bool]
    blockers: tuple[str, ...]

REQUIRED = (
    "ci_green", "paper_validation_green", "safety_gate_green", "reconciliation_green",
    "sandbox_green", "operational_hardening_green", "secrets_absent", "live_disabled",
)

def final_validation(evidence: dict[str, bool] | None = None) -> GoNoGo:
    e = evidence or {}
    checks = {name: bool(e.get(name, False)) for name in REQUIRED}
    blockers = tuple(name for name, ok in checks.items() if not ok)
    return GoNoGo(not blockers, checks, blockers)
