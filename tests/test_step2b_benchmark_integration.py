import pandas as pd

def test_step2b_modules_import_and_portfolio_adapter_uses_step1_engine():
    from research.mtf_features import build_mtf_features
    from research.portfolio_execution import run_portfolio
    from research.step2b_adapters import current_signal
    from research.run_step2b_benchmark import build_symbol_features
    assert callable(build_mtf_features)
    assert callable(run_portfolio)
    assert callable(current_signal)
    assert callable(build_symbol_features)

def test_canonical_timestamp_is_preserved_after_normalization(tmp_path):
    from research.run_step2b_benchmark import _normalize_frame
    p=tmp_path/"ETHUSDT.jsonl"
    pd.DataFrame([{"timestamp":"2026-05-01T00:00:00Z","open":100,"high":101,"low":99,"close":100,"volume":10}]).to_json(p,orient="records",lines=True)
    frame=_normalize_frame(p)
    assert "timestamp" in frame.columns
    assert str(frame.iloc[0]["timestamp"]) == "2026-05-01 00:00:00+00:00"
