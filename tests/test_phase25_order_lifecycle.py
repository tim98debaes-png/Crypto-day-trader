import pytest

from live_execution_contract import ControlledLiveExecutor, LiveOrderRequest, OrderSide, OrderType, SubmissionResult
from live_order_lifecycle import ControlledOrderLifecycle, OrderState, ReconciliationRequired
from prelive_safety_gate import AuthorizationStatus, ExecutionMode, SafetyDecision


class Transport:
    def __init__(self, result=None):
        self.calls = 0
        self.result = result or SubmissionResult(True, "ack", "x")
    def submit(self, request):
        self.calls += 1
        return SubmissionResult(self.result.accepted, self.result.reason, request.client_order_id)


@pytest.fixture
def decision():
    return SafetyDecision(AuthorizationStatus.LIVE_AUTHORIZED, "ok", ExecutionMode.LIVE, True)


def req():
    return LiveOrderRequest("client-1", "BTCUSDT", OrderSide.BUY, OrderType.MARKET, 0.01)


def test_duplicate_submission_is_idempotent(decision):
    transport = Transport()
    lifecycle = ControlledOrderLifecycle(ControlledLiveExecutor(transport))
    first = lifecycle.submit_once(req(), decision)
    second = lifecycle.submit_once(req(), decision)
    assert first.accepted is True
    assert second.accepted is False
    assert second.reason == "idempotent_terminal_order"
    assert transport.calls == 1


def test_transport_timeout_requires_reconciliation(decision):
    class TimeoutTransport:
        def submit(self, request):
            raise TimeoutError("timed out")
    lifecycle = ControlledOrderLifecycle(ControlledLiveExecutor(TimeoutTransport()))
    with pytest.raises(ReconciliationRequired):
        lifecycle.submit_once(req(), decision)
    assert lifecycle.ledger.get("client-1").state is OrderState.UNKNOWN


def test_rejected_order_is_terminal(decision):
    transport = Transport(SubmissionResult(False, "exchange_rejected", "x"))
    lifecycle = ControlledOrderLifecycle(ControlledLiveExecutor(transport))
    result = lifecycle.submit_once(req(), decision)
    assert result.accepted is False
    assert lifecycle.ledger.get("client-1").state is OrderState.REJECTED
    with pytest.raises(AssertionError):
        assert lifecycle.submit_once(req(), decision).accepted
    assert transport.calls == 1
