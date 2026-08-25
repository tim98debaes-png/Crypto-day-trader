"""Phase 26: durable, append-safe order ledger contract.

The ledger is intentionally transport-neutral. It stores sanitized order
state only; credentials and exchange responses containing secrets are never
persisted by this module.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

from live_execution_contract import LiveOrderRequest
from live_order_lifecycle import OrderState


@dataclass(frozen=True)
class DurableOrderRecord:
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    state: str
    exchange_order_id: str | None = None
    reason: str | None = None


class DurableOrderLedger:
    """Atomic JSON persistence with idempotent client-order identity."""

    def __init__(self, path: str):
        self.path = Path(path)
        self._records: dict[str, DurableOrderRecord] = {}
        self._load()

    @staticmethod
    def _record(request: LiveOrderRequest, state: OrderState, exchange_order_id=None, reason=None):
        return DurableOrderRecord(
            request.client_order_id, request.symbol, request.side.value,
            request.order_type.value, float(request.quantity), state.value,
            exchange_order_id, reason,
        )

    def _load(self):
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError("ledger root must be a list")
            for item in data:
                record = DurableOrderRecord(**item)
                if record.client_order_id in self._records:
                    raise ValueError("duplicate client_order_id")
                self._records[record.client_order_id] = record
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("order ledger integrity failure") from exc

    def _persist(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([asdict(r) for r in self._records.values()], sort_keys=True, separators=(",", ":"))
        fd, tmp = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)

    def create(self, request: LiveOrderRequest) -> DurableOrderRecord:
        existing = self._records.get(request.client_order_id)
        if existing:
            return existing
        record = self._record(request, OrderState.NEW)
        self._records[record.client_order_id] = record
        self._persist()
        return record

    def get(self, client_order_id: str) -> DurableOrderRecord | None:
        return self._records.get(client_order_id)

    def transition(self, client_order_id: str, state: OrderState, *, exchange_order_id=None, reason=None) -> DurableOrderRecord:
        record = self._records[client_order_id]
        if record.state in {s.value for s in (OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED)} and state.value != record.state:
            raise ValueError("terminal order cannot transition")
        updated = DurableOrderRecord(record.client_order_id, record.symbol, record.side, record.order_type, record.quantity, state.value, exchange_order_id or record.exchange_order_id, reason or record.reason)
        self._records[client_order_id] = updated
        self._persist()
        return updated

    def all(self) -> list[DurableOrderRecord]:
        return list(self._records.values())
