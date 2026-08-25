from live_execution_contract import LiveOrderRequest, OrderSide, OrderType
from live_order_lifecycle import OrderState
from durable_order_ledger import DurableOrderLedger


def request():
    return LiveOrderRequest("durable-1", "BTCUSDT", OrderSide.BUY, OrderType.MARKET, 0.01)


def test_ledger_survives_restart(tmp_path):
    path = tmp_path / "orders.json"
    ledger = DurableOrderLedger(str(path))
    ledger.create(request())
    ledger.transition("durable-1", OrderState.ACKNOWLEDGED, exchange_order_id="ex-1")
    restored = DurableOrderLedger(str(path))
    record = restored.get("durable-1")
    assert record.state == OrderState.ACKNOWLEDGED.value
    assert record.exchange_order_id == "ex-1"


def test_duplicate_client_id_is_idempotent(tmp_path):
    ledger = DurableOrderLedger(str(tmp_path / "orders.json"))
    first = ledger.create(request())
    second = ledger.create(request())
    assert first == second
    assert len(ledger.all()) == 1


def test_corrupt_ledger_fails_closed(tmp_path):
    path = tmp_path / "orders.json"
    path.write_text("not-json", encoding="utf-8")
    try:
        DurableOrderLedger(str(path))
    except RuntimeError as exc:
        assert "integrity" in str(exc)
    else:
        raise AssertionError("corrupt ledger must fail closed")
