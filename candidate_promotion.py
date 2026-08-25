"""Controlled promotion of optimizer candidates into paper-trading eligibility.

Promotion is intentionally separate from order execution. A candidate must pass
walk-forward out-of-sample metrics, the existing paper quality gate, and an
explicit human approval flag. No live order is placed by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from paper_router import candidate_is_approved


@dataclass(frozen=True)
class PromotionDecision:
    status: str
    reason: str
    candidate: dict
    promoted_at: str | None = None

    @property
    def approved(self) -> bool:
        return self.status == "PROMOTED"


def _test_metrics(candidate: dict) -> dict[str, Any]:
    test = candidate.get("test") or {}
    return {
        "OOS %": test.get("return_pct", candidate.get("OOS %")),
        "OOS PF": test.get("profit_factor", candidate.get("OOS PF")),
        "OOS trades": test.get("closed_trades", candidate.get("OOS trades")),
        # Existing router gate expresses drawdown as a negative percentage.
        "OOS DD": -abs(float(test.get("max_drawdown_pct", 0.0)))
        if test.get("max_drawdown_pct") is not None
        else candidate.get("OOS DD"),
        "Stability": candidate.get("Stability", candidate.get("Neighbour Stability")),
        "MC P05 %": candidate.get("MC P05 %", candidate.get("MC P05")),
        "Status": candidate.get("Status", "ROBUST"),
    }


def promotion_candidate(candidate: dict) -> dict:
    """Normalize a walk-forward candidate to the production gate contract."""
    normalized = dict(candidate)
    normalized.update(_test_metrics(candidate))
    return normalized


def promote_candidate(candidate: dict, human_approved: bool = False) -> PromotionDecision:
    """Promote only after all automated gates and explicit human approval pass."""
    if not isinstance(candidate, dict) or not candidate:
        return PromotionDecision("BLOCKED", "invalid_candidate", {})
    if not human_approved:
        return PromotionDecision("BLOCKED", "human_approval_required", dict(candidate))

    normalized = promotion_candidate(candidate)
    required = ("OOS %", "OOS PF", "OOS trades", "OOS DD", "Stability", "MC P05 %")
    if any(normalized.get(key) is None for key in required):
        return PromotionDecision("BLOCKED", "missing_validation_metrics", dict(candidate))

    if not candidate_is_approved(normalized):
        return PromotionDecision("BLOCKED", "quality_gates_failed", dict(candidate))

    return PromotionDecision(
        "PROMOTED",
        "all_gates_passed",
        dict(candidate),
        datetime.now(timezone.utc).isoformat(),
    )
