"""Phase 25: transport-neutral live execution contract.

This module defines the boundary a future exchange adapter must implement. It
contains no exchange SDK and cannot place an order itself. Authorization is
re-checked immediately before submission and the adapter must receive an
immutable request plus a safety decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from prelive_safety_gate import SafetyDecision, AuthorizationStatus, ExecutionMode


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass(frozen=True)
class LiveOrderRequest:
    client_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    limit_price: float | None = None


@dataclass(frozen=True)
class SubmissionResult:
    accepted: bool
    reason: str
    client_order_id: str


class LiveTransport(Protocol):
    """Minimal future exchange adapter contract; implementations live elsewhere."""

    def submit(self, request: LiveOrderRequest) -> SubmissionResult: ...


class ControlledLiveExecutor:
    """Safety wrapper around a future transport; rejects paper/invalid requests."""

    def __init__(self, transport: LiveTransport):
        self.transport = transport

    def submit(self, request: LiveOrderRequest, decision: SafetyDecision) -> SubmissionResult:
        if decision.mode is not ExecutionMode.LIVE:
            return SubmissionResult(False, "execution_mode_not_live", request.client_order_id)
        if decision.status is not AuthorizationStatus.LIVE_AUTHORIZED or not decision.live_authorized:
            return SubmissionResult(False, "safety_gate_not_authorized", request.client_order_id)
        if not request.client_order_id or not request.symbol or request.quantity <= 0:
            return SubmissionResult(False, "invalid_order_request", request.client_order_id)
        if request.order_type is OrderType.LIMIT and (request.limit_price is None or request.limit_price <= 0):
            return SubmissionResult(False, "invalid_limit_price", request.client_order_id)
        return self.transport.submit(request)
