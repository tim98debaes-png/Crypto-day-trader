"""Phase 31 portfolio recovery and failure-mode validation."""

from paper_portfolio import PaperPortfolio


def candidate():
    return {
        "Status": "ROBUST",
        "OOS %": 10,
        "OOS PF": 1.5,
        "OOS trades": 25,
        "OOS DD": -10,
        "Stability": 80,
        "MC P05 %": 5,
        "Strategy Params": {"sl_atr": 2.0, "rr": 2.0},
    }


def market(price=100.0, symbol="BTCUSDT"):
    return {
        "symbol": symbol,
        "price": price,
        "timestamp": "2026-08-26T09:00:00+00:00",
    }


def test_phase31_portfolio_persists_open_position_and_restores(tmp_path):
    state = tmp_path / "portfolio.json"
    portfolio = PaperPortfolio(
        capital=1000,
        coins=["BTCUSDT"],
        persist=True,
        state_path=str(state),
        fee_pct=0,
        slippage_pct=0,
    )
    result = portfolio.process(
        "BTCUSDT", candidate(), market(),
        {"long_score": 3, "short_score": 0, "stop_distance": 2, "rr": 2},
    )
    assert result["action"] == "OPEN"
    portfolio.save_state()

    restored = PaperPortfolio(
        capital=1000,
        coins=["BTCUSDT"],
        persist=True,
        state_path=str(state),
        fee_pct=0,
        slippage_pct=0,
    )
    assert restored.account("BTCUSDT").position is not None
    assert restored.account("BTCUSDT").position.direction == "LONG"


def test_phase31_invalid_market_price_fails_safe(tmp_path):
    portfolio = PaperPortfolio(
        capital=1000,
        coins=["BTCUSDT"],
        persist=False,
        state_path=str(tmp_path / "portfolio.json"),
    )
    try:
        portfolio.process(
            "BTCUSDT", candidate(), market(price=0),
            {"long_score": 3, "short_score": 0, "stop_distance": 2, "rr": 2},
        )
    except ValueError as exc:
        assert str(exc) == "market price must be positive"
    else:
        raise AssertionError("invalid market price must be rejected")


def test_phase31_no_signal_does_not_open_position(tmp_path):
    portfolio = PaperPortfolio(
        capital=1000,
        coins=["BTCUSDT"],
        persist=False,
        state_path=str(tmp_path / "portfolio.json"),
    )
    result = portfolio.process(
        "BTCUSDT", candidate(), market(),
        {"long_score": 0, "short_score": 0, "stop_distance": 2, "rr": 2},
    )
    assert result["action"] == "SKIP"
    assert result["reason"] == "no_direction"
    assert portfolio.account("BTCUSDT").position is None
