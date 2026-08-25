"""Phase 28 deterministic exchange sandbox; never reaches a real exchange."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from live_execution_contract import LiveOrderRequest, SubmissionResult

class SandboxScenario(str, Enum):
    ACK = "ACK"
    REJECT = "REJECT"
    TIMEOUT = "TIMEOUT"
    PARTIAL = "PARTIAL"
    RATE_LIMIT = "RATE_LIMIT"

@dataclass(frozen=True)
class SandboxFill:
    quantity: float
    price: float

class ExchangeSandbox:
    def __init__(self, scenario: SandboxScenario = SandboxScenario.ACK, fill_ratio: float = 1.0, price: float = 100.0):
        self.scenario = scenario
        self.fill_ratio = fill_ratio
        self.price = price
        self.calls = 0

    def submit(self, request: LiveOrderRequest) -> SubmissionResult:
        self.calls += 1
        if self.scenario is SandboxScenario.TIMEOUT:
            raise TimeoutError("sandbox transport timeout")
        if self.scenario is SandboxScenario.REJECT:
            return SubmissionResult(False, "sandbox_rejected", request.client_order_id)
        if self.scenario is SandboxScenario.RATE_LIMIT:
            return SubmissionResult(False, "sandbox_rate_limited", request.client_order_id)
        return SubmissionResult(True, "sandbox_ack", request.client_order_id)

    def fill(self, request: LiveOrderRequest) -> SandboxFill:
        ratio = min(max(float(self.fill_ratio), 0.0), 1.0)
        return SandboxFill(request.quantity * ratio, self.price)
