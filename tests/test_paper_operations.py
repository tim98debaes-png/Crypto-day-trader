from datetime import datetime, timezone

from paper_engine import PaperAccount
from paper_operations import build_operations_status, event_summary, session_identity
from paper_portfolio import PaperPortfolio


def test_session_identity_is_stable_for_same_config():
    first = PaperPortfolio(capital=1000, coins=["BTCUSDT"], persist=False)
    second = PaperPortfolio(capital=1000, coins=["BTCUSDT"], persist=False)
    assert session_identity(first) == session_identity(second)


def test_session_identity_changes_when_configuration_changes():
    first = PaperPortfolio(capital=1000, coins=["BTCUSDT"], persist=False)
    second = PaperPortfolio(capital=2000, coins=["BTCUSDT"], persist=False)
    assert session_identity(first) != session_identity(second)


def test_operations_status_is_read_only_and_reports_simulation():
    portfolio = PaperPortfolio(capital=1000, coins=["BTCUSDT"], persist=False)
    before = list(portfolio.audit_log())
    status = build_operations_status(portfolio, {"BTCUSDT": 100.0})
    assert status["schema_version"] == 1
    assert status["simulation_only"] is True
    assert status["health"] == "WATCH"
    assert status["open_positions"] == 0
    assert portfolio.audit_log() == before


def test_event_summary_groups_direction_and_symbol():
    account = PaperAccount(capital=1000, cash=1000)
    account.open_position("BTCUSDT", "LONG", 100, 2, 2, "2026-08-24T10:00:00+00:00")
    account.close_position(104, "TARGET", "2026-08-24T10:05:00+00:00")
    portfolio = PaperPortfolio(capital=1000, coins=["BTCUSDT"], persist=False)
    portfolio.accounts["BTCUSDT"] = account

    summary = event_summary(portfolio)
    assert summary["by_event"]["OPEN"] == 1
    assert summary["by_event"]["CLOSE"] == 1
    assert summary["by_direction"]["LONG"] == 2
    assert summary["by_symbol"]["BTCUSDT"] == 2


def test_blocked_status_when_daily_loss_limit_is_reached():
    portfolio = PaperPortfolio(capital=1000, coins=["BTCUSDT"], persist=False)
    account = PaperAccount(capital=1000, cash=970, max_daily_loss_pct=3.0)
    portfolio.accounts["BTCUSDT"] = account
    status = build_operations_status(
        portfolio,
        {"BTCUSDT": 100.0},
        datetime.now(timezone.utc),
    )
    assert status["blocked_accounts"] == 1
    assert status["health"] == "BLOCKED"
