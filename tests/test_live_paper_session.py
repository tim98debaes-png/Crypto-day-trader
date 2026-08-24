from live_paper_session import LivePaperSession
from market_feed import MarketSnapshot


class FakeFeed:
    def snapshot(self, symbol):
        return MarketSnapshot(symbol=symbol, price=100.0, timestamp="2026-08-24T20:00:00+00:00")


def approved_candidate():
    return {
        "approved": True,
        "validation_score": 0.9,
        "robustness_score": 0.9,
        "signal_threshold": 1.0,
        "rr": 2.0,
    }


def test_live_session_reads_market_and_stays_paper_only():
    session = LivePaperSession(["BTCUSDT", "ETHUSDT"], interval_seconds=1)
    session.feed = FakeFeed()

    def candidate_provider(symbol, snapshot):
        return approved_candidate()

    def indicator_provider(symbol, snapshot):
        return {"long_score": 0.0, "short_score": 0.0, "stop_distance": 1.0, "rr": 2.0}

    result = session.tick(candidate_provider, indicator_provider)

    assert set(result) == {"BTCUSDT", "ETHUSDT"}
    assert all(value["action"] == "WAIT" for value in result.values())
    assert all(account.position is None for account in session.accounts.values())
    assert all(account.audit_log == [] for account in session.accounts.values())


def test_live_session_can_open_from_validated_signal():
    session = LivePaperSession(["BTCUSDT"], interval_seconds=1)
    session.feed = FakeFeed()

    result = session.tick(
        lambda symbol, snapshot: approved_candidate(),
        lambda symbol, snapshot: {"long_score": 2.0, "short_score": 0.0, "stop_distance": 1.0, "rr": 2.0},
    )

    assert result["BTCUSDT"]["action"] == "OPEN"
    assert session.accounts["BTCUSDT"].position is not None
    assert session.accounts["BTCUSDT"].audit_log[0]["event"] == "OPEN"
