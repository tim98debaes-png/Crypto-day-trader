from entry_exit_logic import entry_signal_details
from multi_asset_live_paper_session import _audit_diagnostics
from paper_engine import PaperAccount
from paper_session_monitor import PaperSessionMonitor
from candidate_registry import CandidateRegistry


def test_entry_details_exposes_five_factor_score():
    prices = [100.0, 100.12, 100.24, 100.36, 100.31, 100.43, 100.55, 100.50, 100.62, 100.74, 100.70, 100.82]
    ready, reason, score, confirmations = entry_signal_details(prices)
    assert ready is True
    assert reason == "confirmed"
    assert score == 5
    assert set(confirmations) == {"trend", "price_near_fast", "medium_momentum", "short_momentum", "positive_microstructure"}


def test_tier_b_risk_override_is_half_standard():
    account = PaperAccount(capital=1000.0, fee_pct=0.0, slippage_pct=0.0)
    position = account.open_position("BTCUSDT", "LONG", 100.0, 1.0, 2.0, risk_pct_override=0.25, strategy_score=3, strategy_tier="B")
    assert position.risk_amount == 2.5
    assert account.audit_log[0]["strategy_score"] == 3
    assert account.audit_log[0]["strategy_tier"] == "B"


def test_audit_diagnostics_separates_score_tier_coin_and_exit():
    events = [
        {"event": "OPEN", "symbol": "BTCUSDT", "strategy_score": 3, "strategy_tier": "B"},
        {"event": "CLOSE", "symbol": "BTCUSDT", "pnl": 1.0, "reason": "TP"},
        {"event": "OPEN", "symbol": "ETHUSDT", "strategy_score": 4, "strategy_tier": "A"},
        {"event": "CLOSE", "symbol": "ETHUSDT", "pnl": -2.0, "reason": "SL"},
    ]
    result = _audit_diagnostics(events)
    assert result["score_groups"]["3/5"]["trades"] == 1
    assert result["score_groups"]["4/5"]["losses"] == 1
    assert result["tier_groups"]["B"]["net_pnl"] == 1.0
    assert result["tier_groups"]["A"]["net_pnl"] == -2.0
    assert result["coin_groups"]["BTCUSDT"]["wins"] == 1
    assert result["exit_groups"]["SL"]["losses"] == 1


def test_monitor_uses_rolling_pf_when_window_is_available(tmp_path):
    registry = CandidateRegistry(tmp_path / "registry.json")
    first = registry.register({"Status": "ROBUST", "OOS %": 4, "OOS PF": 1.5, "OOS trades": 20, "OOS DD": -8, "Stability": 75, "MC P05 %": 2})
    registry.promote(first, human_approved=True)
    second = registry.register({"Status": "ROBUST", "OOS %": 4, "OOS PF": 1.5, "OOS trades": 20, "OOS DD": -8, "Stability": 75, "MC P05 %": 2})
    registry.promote(second, human_approved=True)
    monitor = PaperSessionMonitor(registry)
    snapshot = {
        "closed_trades": 25,
        "profit_factor": 2.0,
        "return_pct": 2.0,
        "max_drawdown_pct": 8.0,
        "consecutive_losses": 1,
        "rolling_trades": 20,
        "rolling_profit_factor": 0.8,
        "rolling_consecutive_losses": 1,
    }
    decision = monitor.evaluate(second, snapshot)
    assert decision.status == "WATCH"
    assert "profit_factor" in decision.breaches
