from durable_order_ledger import DurableOrderLedger
from live_execution_contract import LiveOrderRequest, OrderSide, OrderType
from live_order_lifecycle import OrderState
from order_reconciliation import OrderReconciler, RemoteOrder, RemoteOrderState


def req(): return LiveOrderRequest("r-1", "BTCUSDT", OrderSide.BUY, OrderType.MARKET, .01)

class Remote:
    def __init__(self, order): self.order = order
    def find_order(self, client_order_id): return self.order


def test_unknown_remote_state_fails_closed(tmp_path):
    ledger = DurableOrderLedger(str(tmp_path / "o.json")); ledger.create(req()); ledger.transition("r-1", OrderState.UNKNOWN)
    result = OrderReconciler(ledger, Remote(RemoteOrder("r-1", RemoteOrderState.UNKNOWN))).reconcile("r-1")
    assert result.safe_to_continue is False
    assert result.reason == "remote_state_unknown"


def test_remote_fill_is_persisted(tmp_path):
    ledger = DurableOrderLedger(str(tmp_path / "o.json")); ledger.create(req())
    result = OrderReconciler(ledger, Remote(RemoteOrder("r-1", RemoteOrderState.FILLED, "ex-1"))).reconcile("r-1")
    assert result.safe_to_continue is True
    assert ledger.get("r-1").state == OrderState.FILLED.value
    assert ledger.get("r-1").exchange_order_id == "ex-1"


def test_identity_mismatch_blocks(tmp_path):
    ledger = DurableOrderLedger(str(tmp_path / "o.json")); ledger.create(req())
    result = OrderReconciler(ledger, Remote(RemoteOrder("other", RemoteOrderState.FILLED))).reconcile("r-1")
    assert result.safe_to_continue is False
    assert result.reason == "identity_mismatch"
