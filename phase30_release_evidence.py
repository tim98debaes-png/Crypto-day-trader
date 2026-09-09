"""Independent Phase 30 release evidence checks.

The checks are intentionally conservative and fail closed. They inspect the
checked-out repository rather than accepting caller-supplied booleans.
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent

REQUIRED_TESTS = (
    "tests/test_phase30_final_validation.py",
    "tests/test_phase29_readiness.py",
    "tests/test_phase28_exchange_sandbox.py",
    "tests/test_phase28_lifecycle_integration.py",
    "tests/test_phase27_e2e.py",
    "tests/test_phase26_durable_ledger.py",
    "tests/test_phase26_reconciliation.py",
    "tests/test_phase25_live_contract.py",
    "tests/test_phase25_order_lifecycle.py",
    "tests/test_phase24_safety_gate.py",
    "tests/test_phase23_reliability.py",
)

LIVE_PATTERNS = (
    re.compile(r"LIVE[_-]?TRADING\s*=\s*true", re.I),
    re.compile(r"LIVE[_-]?MODE\s*=\s*true", re.I),
    re.compile(r"ENABLE[_-]?LIVE\s*=\s*true", re.I),
    re.compile(r"live_mode\s*=\s*True", re.I),
)
SECRET_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?:api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*[\"'][^\"']{12,}[\"']", re.I),
)


def required_tests_present() -> bool:
    return all((ROOT / path).is_file() for path in REQUIRED_TESTS)


def live_trading_disabled() -> bool:
    """Return False on explicit source-level live-enable markers."""
    for path in ROOT.rglob("*.py"):
        if any(part in {".git", ".venv", "venv", "__pycache__"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in LIVE_PATTERNS):
            return False
    return True


def tracked_secrets_absent() -> bool:
    """Return False when obvious credential material is present in source."""
    ignored = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in ignored for part in path.parts):
            continue
        if path.stat().st_size > 1_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            return False
    return True


def release_evidence() -> dict[str, bool]:
    return {
        "required_tests_present": required_tests_present(),
        "secrets_absent": tracked_secrets_absent(),
        "live_disabled": live_trading_disabled(),
    }


def assert_release_evidence() -> None:
    evidence = release_evidence()
    blockers = tuple(name for name, ok in evidence.items() if not ok)
    if blockers:
        raise SystemExit(f"PHASE30_NO_GO: {', '.join(blockers)}")


if __name__ == "__main__":
    assert_release_evidence()
    print("PHASE30_RELEASE_EVIDENCE=GO")
