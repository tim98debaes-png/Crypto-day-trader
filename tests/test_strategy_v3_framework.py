from strategy_v3 import V3Config, classify_regime, relative_strength, score_setup, position_risk_pct, build_trade_plan
from v3_portfolio_risk import PortfolioSnapshot, admit
from v3_trade_forensics import analyze_trade, summarize
from v3_validation import FoldResult, promotion_gate


def candles(prices, volume=100.0):
    return [{"open": p * .999, "high": p * 1.002, "low": p * .998, "close": p, "volume": volume} for p in prices]


def test_relative_strength_is_asset_minus_benchmark():
    asset = candles([100, 101, 103, 105, 110])
    btc = candles([100, 100.5, 101, 101.5, 102])
    assert relative_strength(asset, btc, 4) > 0


def test_regime_is_known_and_finite():
    prices = [100 + i * 0.5 for i in range(60)]
    r = classify_regime(candles(prices))
    assert r.name in {"TREND_UP", "TREND_DOWN", "RANGE", "HIGH_VOL", "LOW_VOL", "TRANSITION"}
    assert r.confidence >= 0
    assert r.volatility_pct >= 0


def test_setup_score_is_bounded_and_trade_plan_scales_risk():
    p = [100 + i * 0.4 for i in range(70)]
    setup = score_setup(candles(p), candles(p), candles(p), "LONG", candles(p))
    assert setup is not None
    assert 0 <= setup.score <= 1
    risk = position_risk_pct(setup)
    assert 0.15 <= risk <= 0.75
    plan = build_trade_plan(setup, 1000, 128, float(setup.features["atr"]))
    if setup.score >= 0.62:
        assert plan is not None
        assert plan.position_notional > 0


def test_portfolio_rejects_position_and_risk_concentration():
    snapshot = PortfolioSnapshot(1000, ("ETHUSDT", "SOLUSDT", "ADAUSDT", "AVAXUSDT"), 2.0)
    result = admit("BTCUSDT", .5, snapshot, {})
    assert not result.allowed
    assert result.reason == "MAX_POSITIONS"


def test_trade_forensics_exposes_mfe_mae():
    record = analyze_trade("LONG", 100, 104, 4, [100, 98, 103, 106, 104], "TP")
    assert record.mfe_r == 1.5
    assert record.mae_r == -0.5
    summary = summarize([record])
    assert summary["winner_mfe_r_mean"] == 1.5
    assert summary["loser_mfe_r_mean"] == 0.0


def test_promotion_requires_oos_quality():
    folds = [FoldResult(i, 100, 50, 1, 2.0, 1.2, 8.0, .1, 30) for i in range(4)]
    decision = promotion_gate(folds)
    assert decision.eligible


def test_promotion_rejects_negative_expectancy():
    folds = [FoldResult(i, 100, 50, 1, -1.0, .8, 8.0, -.1, 30) for i in range(4)]
    decision = promotion_gate(folds)
    assert not decision.eligible
    assert "NEGATIVE_MEAN_EXPECTANCY" in decision.reasons
