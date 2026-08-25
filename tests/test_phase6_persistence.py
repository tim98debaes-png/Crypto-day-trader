from paper_portfolio import PaperPortfolio


def test_portfolio_persists_closed_trade(tmp_path):
    path = tmp_path / "portfolio.json"

    first = PaperPortfolio(
        capital=1000,
        fee_pct=0,
        slippage_pct=0,
        persist=True,
        state_path=str(path),
    )
    account = first.account("BTCUSDT")
    account.open_position("BTCUSDT", "LONG", 100, 2, 2)
    account.close_position(104, "TP")
    first.summary({"BTCUSDT": 104})

    restored = PaperPortfolio(
        capital=1000,
        fee_pct=0,
        slippage_pct=0,
        persist=True,
        state_path=str(path),
    )
    summary = restored.summary({"BTCUSDT": 104})

    assert summary["closed_trades"] == 1
    assert summary["wins"] == 1
    assert summary["return_pct"] > 0


def test_portfolio_persists_open_position(tmp_path):
    path = tmp_path / "portfolio.json"

    first = PaperPortfolio(
        capital=1000,
        fee_pct=0,
        slippage_pct=0,
        persist=True,
        state_path=str(path),
    )
    account = first.account("ETHUSDT")
    account.open_position("ETHUSDT", "SHORT", 100, 5, 2)
    first.summary({"ETHUSDT": 98})

    restored = PaperPortfolio(
        capital=1000,
        fee_pct=0,
        slippage_pct=0,
        persist=True,
        state_path=str(path),
    )

    position = restored.account("ETHUSDT").position
    assert position is not None
    assert position.direction == "SHORT"
    assert position.entry_price == 100


def test_incompatible_config_does_not_restore(tmp_path):
    path = tmp_path / "portfolio.json"

    first = PaperPortfolio(
        capital=1000,
        fee_pct=0,
        slippage_pct=0,
        persist=True,
        state_path=str(path),
    )
    first.account("BTCUSDT").open_position("BTCUSDT", "LONG", 100, 2, 2)
    first.summary({"BTCUSDT": 100})

    restored = PaperPortfolio(
        capital=2000,
        fee_pct=0,
        slippage_pct=0,
        persist=True,
        state_path=str(path),
    )

    assert restored.accounts == {}
    assert restored.capital == 2000
