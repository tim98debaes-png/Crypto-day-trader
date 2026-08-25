"""Phase 29 deterministic production-readiness and go/no-go checks."""
from __future__ import annotations
from dataclasses import dataclass
import os

@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    checks: dict[str, bool]
    blocked_reasons: tuple[str, ...]

REQUIRED_LIVE_ENV = ("LIVE_TRADING_ENABLED", "LIVE_ACCOUNT_TYPE")

def evaluate_readiness(env=None, *, ci_green=False, disaster_recovery_tested=False, alerts_configured=False):
    source = os.environ if env is None else env
    checks = {
        "ci_green": bool(ci_green),
        "live_disabled_by_default": str(source.get("LIVE_TRADING_ENABLED", "false")).lower() != "true",
        "no_test_account_for_live": str(source.get("LIVE_ACCOUNT_TYPE", "paper")).lower() != "test",
        "alerts_configured": bool(alerts_configured),
        "disaster_recovery_tested": bool(disaster_recovery_tested),
    }
    reasons = tuple(name for name, passed in checks.items() if not passed)
    return ReadinessResult(not reasons, checks, reasons)

def redact_secret(value: str | None) -> str:
    if not value: return ""
    return "***REDACTED***"
