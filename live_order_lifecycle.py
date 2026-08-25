"""Phase 25 order lifecycle, idempotency and reconciliation contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic

from live_execution_contract import LiveOrderRequest, SubmissionResult


class OrderState(str, Enum):
    NEW = "NEW"
    SUBMITTING = "SUBMITTING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


TERMINAL = {OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED}
SUBMISSION_LOCKED = TERMINAL | {OrderState.ACKNOWLEDGED}


@dataclass
class OrderRecord:
    request: LiveOrderRequest
    state: OrderState = OrderState.NEW
    exchange_order_id: str | None = None
    reason: str | None = None
    created_at: float = field(default_factory=monotonic)


class OrderLedger:
    """In-memory contract for an eventual durable/idempotent order ledger."""

    def __init__(self):
        self._records: dict[str, OrderRecord] = {}

    def create(self, request: LiveOrderRequest) -> OrderRecord:
        existing = self._records.get(request.client_order_id)
        if existing is not None:
            return existing
        record = OrderRecord(request=request)
        self._records[request.client_order_id] = record
        return record

    def get(self, client_order_id: str) -> OrderRecord | None:
        return self._records.get(client_order_id)

    def transition(self, client_order_id: str, state: OrderState, *, exchange_order_id: str | None = None, reason: str | None = None) -> OrderRecord:
        record = self._records[client_order_id]
        if record.state in TERMINAL and state != record.state:
            raise ValueError("terminal order cannot transition")
        record.state = state
        if exchange_order_id is not None:
            record.exchange_order_id = exchange_order_id
        if reason is not None:
            record.reason = reason
        return record

    def all(self) -> list[OrderRecord]:
        return list(self._records.values())


class ReconciliationRequired(RuntimeError):
    pass


class ControlledOrderLifecycle:
    """Wrap a controlled executor with idempotency and ambiguous-result handling."""

    def __init__(self, executor):
        self.executor = executor
        self.ledger = OrderLedger()

    def submit_once(self, request: LiveOrderRequest, decision) -> SubmissionResult:
        record = self.ledger.create(request)
        if record.state in SUBMISSION_LOCKED:
            return SubmissionResult(False, "idempotent_terminal_order", request.client_order_id)
        if record.state is OrderState.SUBMITTING or record.state is OrderState.UNKNOWN:
            raise ReconciliationRequired(request.client_order_id)
        self.ledger.transition(request.client_order_id, OrderState.SUBMITTING)
        try:
            result = self.executor.submit(request, decision)
        except TimeoutError:
            self.ledger.transition(request.client_order_id, OrderState.UNKNOWN, reason="transport_timeout")
            raise ReconciliationRequired(request.client_order_id)
        if result.accepted:
            self.ledger.transition(request.client_order_id, OrderState.ACKNOWLEDGED, reason=result.reason)
        else:
            self.ledger.transition(request.client_order_id, OrderState.REJECTED, reason=result.reason)
        return result
