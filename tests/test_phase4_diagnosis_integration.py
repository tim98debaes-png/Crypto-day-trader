from research.phase4_diagnosis import diagnose

def test_phase4_diagnosis_is_deterministic():
    trades=[
        {'event':'CLOSE','symbol':'BTCUSDT','direction':'LONG','reason':'SL','pnl':-2.5,'strategy_tier':'C'},
        {'event':'CLOSE','symbol':'ETHUSDT','direction':'SHORT','reason':'TP','pnl':4.0,'strategy_tier':'C'},
        {'event':'OPEN','symbol':'BTCUSDT','direction':'LONG'},
    ]
    first=diagnose(trades); second=diagnose(trades)
    assert first==second
    assert first['exit_reasons']=={'SL':1,'TP':1}
    assert first['by_symbol']['BTCUSDT']['pnl']==-2.5
