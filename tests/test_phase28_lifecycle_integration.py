import pytest
from exchange_sandbox import ExchangeSandbox, SandboxScenario
from live_execution_contract import ControlledLiveExecutor, LiveOrderRequest, OrderSide, OrderType
from live_order_lifecycle import ControlledOrderLifecycle, ReconciliationRequired, OrderState
from prelive_safety_gate import AuthorizationStatus, ExecutionMode, SafetyDecision

def req(): return LiveOrderRequest("sb-life-1", "BTCUSDT", OrderSide.BUY, OrderType.MARKET, .1)
def decision(): return SafetyDecision(AuthorizationStatus.LIVE_AUTHORIZED, "sandbox_only", ExecutionMode.LIVE, True)

def test_sandbox_rejection_becomes_terminal():
    s=ExchangeSandbox(SandboxScenario.REJECT); l=ControlledOrderLifecycle(ControlledLiveExecutor(s)); r=l.submit_once(req(), decision()); assert not r.accepted; assert l.ledger.get("sb-life-1").state is OrderState.REJECTED

def test_sandbox_timeout_requires_reconciliation():
    s=ExchangeSandbox(SandboxScenario.TIMEOUT); l=ControlledOrderLifecycle(ControlledLiveExecutor(s))
    with pytest.raises(ReconciliationRequired): l.submit_once(req(), decision())
    assert l.ledger.get("sb-life-1").state is OrderState.UNKNOWN

def test_duplicate_after_ack_does_not_resubmit():
    s=ExchangeSandbox(); l=ControlledOrderLifecycle(ControlledLiveExecutor(s)); l.submit_once(req(), decision()); r=l.submit_once(req(), decision()); assert not r.accepted; assert s.calls==1
