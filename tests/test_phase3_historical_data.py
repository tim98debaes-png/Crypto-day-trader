from pathlib import Path

from research.historical_data import _timestamp_ms, fetch_klines, save_jsonl


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        start = params["startTime"]
        return FakeResponse([
            [start, "100", "101", "99", "100.5", "10", start + 299999, "1005", 3, "", "", ""],
        ])


def test_timestamp_parser_accepts_utc_iso():
    assert _timestamp_ms("2026-05-01T00:00:00Z") == 1777593600000


def test_fetch_klines_normalizes_schema_and_bounds():
    session = FakeSession()
    rows = fetch_klines("BTCUSDT", "5m", "2026-05-01T00:00:00Z", "2026-05-01T00:05:00Z", session=session)
    assert len(rows) == 1
    assert rows[0]["open"] == 100.0
    assert rows[0]["close"] == 100.5
    assert rows[0]["volume"] == 10.0
    assert session.calls[0][1]["limit"] == 1000


def test_save_jsonl_writes_one_candle_per_line(tmp_path: Path):
    path = tmp_path / "BTCUSDT.jsonl"
    save_jsonl([{"timestamp": 1, "open": 1.0}], path)
    assert path.read_text(encoding="utf-8").count("\n") == 1
