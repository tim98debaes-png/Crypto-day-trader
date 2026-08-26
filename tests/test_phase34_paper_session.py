from phase34_paper_session import run_bounded_paper_session


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class FakeFeed:
    def __init__(self):
        self.calls = 0

    def snapshot(self, symbol):
        self.calls += 1
        return type("Snapshot", (), {"symbol": symbol.upper(), "price": 100.0 + self.calls, "timestamp": None})()


def test_bounded_paper_session_is_deterministic_and_safe():
    clock = FakeClock()
    feed = FakeFeed()
    result = run_bounded_paper_session(
        symbol="BTCUSDT",
        duration_seconds=30,
        interval_seconds=10,
        feed=feed,
        sleep=clock.sleep,
        clock=clock.now,
    )
    assert result.symbol == "BTCUSDT"
    assert result.samples == 3
    assert result.errors == 0
    assert result.last_price == 103.0
    assert result.summary["open_positions"] == 0
