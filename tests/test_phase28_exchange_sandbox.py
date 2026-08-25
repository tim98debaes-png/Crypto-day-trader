import pytest
from exchange_sandbox import ExchangeSandbox, SandboxScenario
from live_execution_contract import LiveOrderRequest, OrderSide, OrderType

def req(): return LiveOrderRequest("sb-1", "BTCUSDT", OrderSide.BUY, OrderType.MARKET, 1.0)

def test_ack():
    s=ExchangeSandbox(); r=s.submit(req()); assert r.accepted and s.calls==1

def test_reject_and_rate_limit():
    for scenario in (SandboxScenario.REJECT, SandboxScenario.RATE_LIMIT):
        s=ExchangeSandbox(scenario); r=s.submit(req()); assert not r.accepted

def test_timeout_is_explicit():
    with pytest.raises(TimeoutError): ExchangeSandbox(SandboxScenario.TIMEOUT).submit(req())

def test_partial_fill_is_deterministic():
    fill=ExchangeSandbox(SandboxScenario.PARTIAL, fill_ratio=.4, price=123).fill(req())
    assert fill.quantity == .4 and fill.price == 123

def test_sandbox_has_no_external_endpoint():
    assert not hasattr(ExchangeSandbox, "base_url")
