"""Phase 27 deterministic end-to-end paper execution harness."""
from __future__ import annotations
from dataclasses import dataclass
from prelive_safety_gate import PreLiveSafetyGate, SafetyLimits
from live_execution_contract import ControlledLiveExecutor, LiveOrderRequest, OrderSide, OrderType, SubmissionResult
from live_order_lifecycle import ControlledOrderLifecycle, ReconciliationRequired
from durable_order_ledger import DurableOrderLedger
from order_reconciliation import OrderReconciler, RemoteOrder, RemoteOrderState

@dataclass(frozen=True)
class E2EResult:
    passed: bool
    stage: str
    reason: str

class FakeTransport:
    def __init__(self, state=RemoteOrderState.FILLED):
        self.submissions = 0; self.state = state
    def submit(self, request):
        self.submissions += 1
        return SubmissionResult(True, "paper_transport_ack", request.client_order_id)
    def find_order(self, client_order_id):
        return RemoteOrder(client_order_id, self.state, "paper-ex-1")

def run_e2e(path: str) -> E2EResult:
    gate = PreLiveSafetyGate({"LIVE_TRADING_ENABLED": "false"}, SafetyLimits(1000, 2))
    paper = gate.authorize(requested_mode="PAPER")
    transport = FakeTransport()
    lifecycle = ControlledOrderLifecycle(ControlledLiveExecutor(transport))
    ledger = DurableOrderLedger(path)
    request = LiveOrderRequest("e2e-1", "BTCUSDT", OrderSide.BUY, OrderType.MARKET, .01)
    # The integrated harness intentionally proves the paper path without
    # authorizing a live order. A live decision is never fabricated here.
    if paper.live_authorized:
        return E2EResult(False, "safety", "paper_decision_authorized_live")
    blocked = lifecycle.executor.submit(request, paper)
    if blocked.accepted or transport.submissions:
        return E2EResult(False, "safety", "paper_request_reached_transport")
    ledger.create(request)
    reconciler = OrderReconciler(ledger, transport)
    # No remote order exists because no transport submission was made; the
    # reconciliation contract therefore must not invent a fill.
    transport.state = RemoteOrderState.UNKNOWN
    result = reconciler.reconcile("e2e-1")
    if result.safe_to_continue:
        return E2EResult(False, "reconciliation", "unknown_remote_state_not_blocked")
    return E2EResult(True, "complete", "all_boundaries_enforced")
