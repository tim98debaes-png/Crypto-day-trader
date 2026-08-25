from production_readiness import evaluate_readiness, redact_secret
from operational_hardening import AuditEvent, shutdown_state

def test_default_is_not_ready_for_production():
    r=evaluate_readiness({}, ci_green=True, disaster_recovery_tested=True, alerts_configured=True)
    assert r.ready is True

def test_live_enabled_does_not_automatically_make_ready():
    r=evaluate_readiness({"LIVE_TRADING_ENABLED":"true"}, ci_green=True, disaster_recovery_tested=True, alerts_configured=True)
    assert not r.ready and "live_disabled_by_default" in r.blocked_reasons

def test_readiness_requires_operational_proof():
    r=evaluate_readiness({}, ci_green=True, disaster_recovery_tested=False, alerts_configured=True)
    assert not r.ready and "disaster_recovery_tested" in r.blocked_reasons

def test_secret_redaction(): assert redact_secret("supersecret") == "***REDACTED***"
def test_shutdown_blocks_unreconciled_orders(): assert shutdown_state(1, False)=="BLOCKED_RECONCILIATION_REQUIRED"
def test_shutdown_allows_clean_stop(): assert shutdown_state(0, False)=="SAFE_TO_STOP"
def test_audit_event_has_no_secret_fields():
    text=AuditEvent("ORDER_ACK","c1","ACKNOWLEDGED","ok").to_json(); assert "secret" not in text.lower()
