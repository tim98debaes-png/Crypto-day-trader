from prelive_safety_gate import AuthorizationStatus, ExecutionMode, SafetyDecision
from live_execution_contract import ControlledLiveExecutor, LiveOrderRequest, OrderSide, OrderType, SubmissionResult


class RecordingTransport:
    def __init__(self): self.calls = []
    def submit(self, request):
        self.calls.append(request)
        return SubmissionResult(True, "submitted_to_transport", request.client_order_id)


def request():
    return LiveOrderRequest("test-1", "BTCUSDT", OrderSide.BUY, OrderType.MARKET, 0.01)


def test_executor_rejects_paper_decision_without_transport_call():
    transport = RecordingTransport()
    executor = ControlledLiveExecutor(transport)
    decision = SafetyDecision(AuthorizationStatus.PAPER_ALLOWED, "paper_mode", ExecutionMode.PAPER)
    result = executor.submit(request(), decision)
    assert result.accepted is False
    assert result.reason == "execution_mode_not_live"
    assert transport.calls == []


def test_executor_rejects_unauthorized_live_decision():
    transport = RecordingTransport()
    executor = ControlledLiveExecutor(transport)
    decision = SafetyDecision(AuthorizationStatus.LIVE_BLOCKED, "live_disabled", ExecutionMode.LIVE)
    result = executor.submit(request(), decision)
    assert result.accepted is False
    assert result.reason == "safety_gate_not_authorized"
    assert transport.calls == []


def test_executor_allows_only_fully_authorized_request():
    transport = RecordingTransport()
    executor = ControlledLiveExecutor(transport)
    decision = SafetyDecision(AuthorizationStatus.LIVE_AUTHORIZED, "all_safety_checks_passed", ExecutionMode.LIVE, True)
    result = executor.submit(request(), decision)
    assert result.accepted is True
    assert len(transport.calls) == 1


def test_invalid_order_is_rejected_before_transport():
    transport = RecordingTransport()
    executor = ControlledLiveExecutor(transport)
    decision = SafetyDecision(AuthorizationStatus.LIVE_AUTHORIZED, "all_safety_checks_passed", ExecutionMode.LIVE, True)
    bad = LiveOrderRequest("", "BTCUSDT", OrderSide.BUY, OrderType.MARKET, 0)
    result = executor.submit(bad, decision)
    assert result.accepted is False
    assert result.reason == "invalid_order_request"
    assert transport.calls == []
