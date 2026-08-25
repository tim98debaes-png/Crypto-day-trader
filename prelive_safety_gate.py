"""Deterministic fail-closed authorization gate for future live execution."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Any


class ExecutionMode(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"


class AuthorizationStatus(str, Enum):
    PAPER_ALLOWED = "PAPER_ALLOWED"
    LIVE_BLOCKED = "LIVE_BLOCKED"
    LIVE_AUTHORIZED = "LIVE_AUTHORIZED"


@dataclass(frozen=True)
class SafetyLimits:
    max_notional: float = 0.0
    max_daily_loss_pct: float = 0.0


@dataclass(frozen=True)
class SafetyDecision:
    status: AuthorizationStatus
    reason: str
    mode: ExecutionMode
    live_authorized: bool = False


class PreLiveSafetyGate:
    """Central safety boundary; defaults and ambiguity always fail closed."""

    def __init__(self, config: Mapping[str, Any] | None = None, limits: SafetyLimits | None = None):
        self.config = dict(config or {})
        self.limits = limits or SafetyLimits()

    def authorize(self, *, requested_mode: str | ExecutionMode,
                  environment: str | None = None,
                  account_type: str | None = None,
                  kill_switch: bool = False,
                  daily_loss_pct: float = 0.0,
                  notional: float = 0.0) -> SafetyDecision:
        try:
            mode = ExecutionMode(str(requested_mode).upper())
        except ValueError:
            return SafetyDecision(AuthorizationStatus.LIVE_BLOCKED, "invalid_execution_mode", ExecutionMode.PAPER)

        if mode is ExecutionMode.PAPER:
            return SafetyDecision(AuthorizationStatus.PAPER_ALLOWED, "paper_mode", mode, False)

        if kill_switch:
            return SafetyDecision(AuthorizationStatus.LIVE_BLOCKED, "kill_switch_active", mode)
        if str(self.config.get("LIVE_TRADING_ENABLED", "false")).lower() != "true":
            return SafetyDecision(AuthorizationStatus.LIVE_BLOCKED, "live_disabled", mode)
        if environment != "production":
            return SafetyDecision(AuthorizationStatus.LIVE_BLOCKED, "environment_not_production", mode)
        if account_type != "live":
            return SafetyDecision(AuthorizationStatus.LIVE_BLOCKED, "account_type_not_live", mode)
        if notional <= 0 or self.limits.max_notional <= 0 or notional > self.limits.max_notional:
            return SafetyDecision(AuthorizationStatus.LIVE_BLOCKED, "notional_limit", mode)
        if daily_loss_pct > 0 and (self.limits.max_daily_loss_pct <= 0 or daily_loss_pct >= self.limits.max_daily_loss_pct):
            return SafetyDecision(AuthorizationStatus.LIVE_BLOCKED, "daily_loss_limit", mode)

        return SafetyDecision(AuthorizationStatus.LIVE_AUTHORIZED, "all_safety_checks_passed", mode, True)
