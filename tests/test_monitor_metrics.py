from monitor_metrics import evaluate_metrics


def base(**overrides):
    data = {
        "closed_trades": 13,
        "winning_trades": 13,
        "losing_trades": 0,
        "ending_equity": 1142.51,
        "return_pct": 14.251,
        "max_drawdown_pct": 2.53,
        "profit_factor": "Infinity",
    }
    data.update(overrides)
    return data


def test_small_sample_is_insufficient_not_invalid():
    decision = evaluate_metrics(base())
    assert decision.status == "INSUFFICIENT_DATA"
    assert decision.metrics_valid is True
    assert decision.statistically_ready is False


def test_ready_after_minimum_sample():
    decision = evaluate_metrics(base(closed_trades=30, winning_trades=25, losing_trades=5, profit_factor=2.4))
    assert decision.status == "READY"
    assert decision.statistically_ready is True


def test_reconciliation_error_is_blocked():
    decision = evaluate_metrics(base(winning_trades=12, losing_trades=0))
    assert decision.status == "BLOCKED"
    assert "reconcile" in decision.reason


def test_missing_metric_is_blocked():
    data = base()
    del data["ending_equity"]
    decision = evaluate_metrics(data)
    assert decision.status == "BLOCKED"
