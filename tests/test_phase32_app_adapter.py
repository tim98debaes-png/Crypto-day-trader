"""Phase 32 application adapter integration contracts."""

from phase32_app_adapter import build_app_dashboard_snapshot


class Portfolio:
    def __init__(self):
        self.positions = {"BTCUSDT": {"qty": 1}, "ETHUSDT": {"qty": 2}}
        self.equity = 1250.0
        self.drawdown_pct = -3.5


def test_app_adapter_maps_existing_portfolio_read_only():
    portfolio = Portfolio()
    snapshot = build_app_dashboard_snapshot(
        active_candidate={"id": "candidate-7", "status": "ACTIVE"},
        portfolio=portfolio,
        allow_new_entries=True,
        heartbeat_age_seconds=10,
    )
    assert snapshot.open_positions == 2
    assert snapshot.equity == 1250.0
    assert snapshot.drawdown_pct == -3.5
    assert snapshot.allow_new_entries is True
    assert snapshot.active_candidate_id == "candidate-7"
    assert portfolio.positions == {"BTCUSDT": {"qty": 1}, "ETHUSDT": {"qty": 2}}


def test_mapping_portfolio_fallback_is_supported():
    portfolio = {
        "positions": {"BTCUSDT": {"qty": 1}},
        "equity": 900.0,
        "drawdown_pct": -12.0,
    }
    snapshot = build_app_dashboard_snapshot(
        active_candidate=None,
        portfolio=portfolio,
        allow_new_entries=False,
        heartbeat_age_seconds=400,
    )
    assert snapshot.open_positions == 1
    assert snapshot.equity == 900.0
    assert snapshot.status == "DEGRADED"
    assert snapshot.allow_new_entries is False
