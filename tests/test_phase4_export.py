from types import SimpleNamespace
import json
from research.phase4_export import export_result

def test_export_result_writes_trade_diagnosis_and_equity(tmp_path):
    result=SimpleNamespace(trades=[{'event':'CLOSE','symbol':'BTCUSDT','direction':'LONG','reason':'TP','pnl':2.0,'strategy_tier':'C'}],equity_curve=[{'timestamp':'2026-01-01T00:00:00Z','equity':1002.0}])
    diagnosis=export_result(result,tmp_path)
    assert diagnosis['trades']==1
    assert json.loads((tmp_path/'trades.json').read_text())
    assert json.loads((tmp_path/'diagnosis.json').read_text())['gross_profit']==2.0
    assert json.loads((tmp_path/'equity_curve.json').read_text())[0]['equity']==1002.0
