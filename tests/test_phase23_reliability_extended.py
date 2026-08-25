from paper_engine import PaperAccount
from phase23_reliability import PaperReliabilityHarness


def markets(count=90):
    return [
        {"symbol": "BTCUSDT", "price": 100.0 + (i % 7), "timestamp": f"2026-08-25T10:{i // 60:02d}:{i % 60:02d}+00:00"}
        for i in range(count)
    ]


def test_multiple_restarts_preserve_checkpoint_and_candidate_identity(tmp_path):
    harness = PaperReliabilityHarness(PaperAccount, str(tmp_path / "obs.json"))
    report = harness.run(
        markets(),
        restart_points=[15, 45, 75],
        active_candidate_id="candidate-stable",
    )
    assert report.passed, report.to_dict()
    assert report.restarts == 3
    assert report.checkpoints == 90


def test_malformed_market_is_reported_not_crashed(tmp_path):
    harness = PaperReliabilityHarness(PaperAccount, str(tmp_path / "obs.json"))
    report = harness.run([
        {"symbol": "BTCUSDT", "price": "bad", "timestamp": "2026-08-25T10:00:00+00:00"},
        {"symbol": "BTCUSDT", "price": 100.0, "timestamp": "2026-08-25T10:01:00+00:00"},
    ])
    assert not report.passed
    assert report.checkpoints == 1
    assert any(v.check == "market_price" for v in report.violations)


def test_checkpoint_completeness_is_part_of_pass_criteria(tmp_path):
    harness = PaperReliabilityHarness(PaperAccount, str(tmp_path / "obs.json"))
    report = harness.run(markets(12), restart_after=6)
    assert report.passed
    assert report.checkpoints == report.events == 12
