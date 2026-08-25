"""Phase 26 reconciliation contract: unknown orders fail closed."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from live_order_lifecycle import OrderState
from durable_order_ledger import DurableOrderLedger

class RemoteOrderState(str, Enum):
    UNKNOWN = "UNKNOWN"
    OPEN = "OPEN"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

@dataclass(frozen=True)
class RemoteOrder:
    client_order_id: str
    state: RemoteOrderState
    exchange_order_id: str | None = None

class ReconciliationTransport(Protocol):
    def find_order(self, client_order_id: str) -> RemoteOrder: ...

class ReconciliationResult:
    def __init__(self, client_order_id: str, state: OrderState | None, safe_to_continue: bool, reason: str):
        self.client_order_id = client_order_id
        self.state = state
        self.safe_to_continue = safe_to_continue
        self.reason = reason

class OrderReconciler:
    def __init__(self, ledger: DurableOrderLedger, transport: ReconciliationTransport):
        self.ledger = ledger
        self.transport = transport

    def reconcile(self, client_order_id: str) -> ReconciliationResult:
        local = self.ledger.get(client_order_id)
        if local is None:
            return ReconciliationResult(client_order_id, None, False, "local_order_missing")
        remote = self.transport.find_order(client_order_id)
        if remote.client_order_id != client_order_id:
            return ReconciliationResult(client_order_id, None, False, "identity_mismatch")
        mapping = {
            RemoteOrderState.OPEN: OrderState.ACKNOWLEDGED,
            RemoteOrderState.FILLED: OrderState.FILLED,
            RemoteOrderState.CANCELLED: OrderState.CANCELLED,
            RemoteOrderState.REJECTED: OrderState.REJECTED,
        }
        if remote.state is RemoteOrderState.UNKNOWN:
            return ReconciliationResult(client_order_id, None, False, "remote_state_unknown")
        state = mapping[remote.state]
        self.ledger.transition(client_order_id, state, exchange_order_id=remote.exchange_order_id, reason="reconciled")
        return ReconciliationResult(client_order_id, state, True, "reconciled")
