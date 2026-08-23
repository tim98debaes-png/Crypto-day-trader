from pathlib import Path


def test_optimizer_integration_contract_is_present():
    app = Path("app.py").read_text(encoding="utf-8")
    assert "phase4_monte_carlo" in app
    assert "phase4_robustness_score" in app
    assert '"MC Robustness"' in app
    assert "phase4_mc_score" in app


def test_robustness_engine_is_separate_from_legacy_mc():
    engine = Path("robustness_engine.py").read_text(encoding="utf-8")
    assert "def monte_carlo(" in engine
    assert "def robustness_score(" in engine
