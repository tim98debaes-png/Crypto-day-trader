from research.phase4_diagnosis import diagnose

def test_diagnose_separates_symbols_directions_and_reasons():
    trades=[
      {'event':'CLOSE','symbol':'BTCUSDT','direction':'LONG','reason':'TP','pnl':10,'strategy_tier':'C'},
      {'event':'CLOSE','symbol':'BTCUSDT','direction':'LONG','reason':'SL','pnl':-5,'strategy_tier':'C'},
      {'event':'CLOSE','symbol':'ETHUSDT','direction':'SHORT','reason':'SL','pnl':-3,'strategy_tier':'B'},
    ]
    out=diagnose(trades)
    assert out['trades']==3 and out['wins']==1 and out['losses']==2
    assert out['by_symbol']['BTCUSDT']['pnl']==5
    assert out['by_direction']['SHORT']['losses']==1
    assert out['by_exit_reason']['SL']['trades']==2

def test_diagnose_ignores_open_events():
    out=diagnose([{'event':'OPEN','symbol':'BTCUSDT'},{'event':'CLOSE','symbol':'BTCUSDT','pnl':2}])
    assert out['trades']==1 and out['gross_profit']==2
