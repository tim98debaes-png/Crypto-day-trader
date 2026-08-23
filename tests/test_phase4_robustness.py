from robustness_engine import max_drawdown, monte_carlo, robustness_score


def test_max_drawdown_uses_peak_to_trough():
    assert max_drawdown([100, 120, 90, 110, 80]) == -33.33333333333333


def test_monte_carlo_is_deterministic_with_seed():
    returns = [2.0, 1.0, -0.5, 1.5, -1.0, 0.8, 1.2, -0.7, 2.1, -0.4, 0.6, 1.0]
    first = monte_carlo(returns, simulations=250, seed=7)
    second = monte_carlo(returns, simulations=250, seed=7)
    assert first == second
    assert first["status"] == "OK"
    assert first["simulations"] == 250


def test_insufficient_trade_sample_is_rejected():
    result = monte_carlo([1.0, -1.0] * 4, simulations=100)
    assert result["status"] == "INSUFFICIENT_TRADES"
    assert robustness_score(result) == 0.0


def test_profitable_stable_distribution_scores_above_zero():
    returns = [1.0, 1.2, 0.8, 1.1, -0.3] * 20
    result = monte_carlo(returns, simulations=500, seed=11)
    score = robustness_score(result)
    assert result["status"] == "OK"
    assert 0.0 <= score <= 100.0
    assert result["probability_profit"] > 0.90


def test_robustness_score_penalizes_bad_downside():
    good = {
        "status": "OK",
        "probability_profit": 0.95,
        "terminal_return_p05": 5.0,
        "max_drawdown_p95": -10.0,
    }
    bad = {
        "status": "OK",
        "probability_profit": 0.55,
        "terminal_return_p05": -30.0,
        "max_drawdown_p95": -45.0,
    }
    assert robustness_score(good) > robustness_score(bad)
