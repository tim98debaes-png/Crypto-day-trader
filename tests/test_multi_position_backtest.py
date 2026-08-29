from multi_position_backtest import MultiPositionBacktester


def test_multiple_symbols_can_be_open_simultaneously():
    rows=[
        {'timestamp':'2026-01-01T00:00:00+00:00','symbol':'AAA','open':100,'high':100,'low':100,'close':100},
        {'timestamp':'2026-01-01T00:00:00+00:00','symbol':'BBB','open':200,'high':200,'low':200,'close':200},
        {'timestamp':'2026-01-01T00:01:00+00:00','symbol':'AAA','open':100,'high':101,'low':99,'close':100.5},
        {'timestamp':'2026-01-01T00:01:00+00:00','symbol':'BBB','open':200,'high':202,'low':198,'close':201},
    ]
    def signal(row):
        if row['timestamp'].endswith('00:00:00+00:00'):
            return {'action':'LONG','stop_distance':1.0,'rr':2.0}
        return {'action':'WAIT'}
    result=MultiPositionBacktester(risk_pct=0.5).run(rows,signal)
    opens=[e for e in result.trades if e.get('event')=='OPEN']
    assert {e['symbol'] for e in opens}=={'AAA','BBB'}


def test_intrabar_stop_closes_without_close_crossing_stop():
    rows=[
        {'timestamp':'2026-01-01T00:00:00+00:00','symbol':'AAA','close':100,'high':100,'low':100},
        {'timestamp':'2026-01-01T00:01:00+00:00','symbol':'AAA','close':100,'high':101,'low':98},
    ]
    result=MultiPositionBacktester(risk_pct=0.5).run(rows,lambda r: {'action':'LONG','stop_distance':1,'rr':2} if r['timestamp'].endswith('00:00:00+00:00') else {'action':'WAIT'})
    closes=[e for e in result.trades if e.get('event')=='CLOSE']
    assert closes and closes[0]['reason']=='SL'


def test_both_stop_and_target_is_conservative_stop():
    rows=[
        {'timestamp':'2026-01-01T00:00:00+00:00','symbol':'AAA','close':100,'high':100,'low':100},
        {'timestamp':'2026-01-01T00:01:00+00:00','symbol':'AAA','close':100,'high':102,'low':98},
    ]
    result=MultiPositionBacktester(risk_pct=0.5).run(rows,lambda r: {'action':'LONG','stop_distance':1,'rr':1} if r['timestamp'].endswith('00:00:00+00:00') else {'action':'WAIT'})
    closes=[e for e in result.trades if e.get('event')=='CLOSE']
    assert closes and closes[0]['reason']=='SL'
