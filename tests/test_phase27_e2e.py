from phase27_e2e import run_e2e


def test_full_chain_fails_closed_without_live_authorization(tmp_path):
    result = run_e2e(str(tmp_path / "orders.json"))
    assert result.passed, result
    assert result.stage == "complete"


def test_harness_does_not_submit_paper_order(tmp_path):
    result = run_e2e(str(tmp_path / "orders.json"))
    assert result.passed
