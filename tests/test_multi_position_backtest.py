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


def test_entry_signal_executes_on_next_candle_open_not_signal_close():
    rows=[
        {'timestamp':'2026-01-01T00:00:00+00:00','symbol':'AAA','open':100,'high':101,'low':99,'close':100},
        {'timestamp':'2026-01-01T00:01:00+00:00','symbol':'AAA','open':110,'high':112,'low':109,'close':111},
        {'timestamp':'2026-01-01T00:02:00+00:00','symbol':'AAA','open':111,'high':111,'low':111,'close':111},
    ]
    def signal(row):
        return {'action':'LONG','stop_distance':1.0,'rr':2.0} if row['timestamp'].endswith('00:00:00+00:00') else {'action':'WAIT'}
    result=MultiPositionBacktester(risk_pct=0.5, slippage_pct=0).run(rows,signal)
    opens=[e for e in result.trades if e.get('event')=='OPEN']
    assert len(opens)==1
    assert opens[0]['timestamp']=='2026-01-01T00:01:00+00:00'
    assert opens[0]['price']==110


def test_signal_on_final_candle_is_not_executed_without_next_open():
    rows=[
        {'timestamp':'2026-01-01T00:00:00+00:00','symbol':'AAA','open':100,'high':100,'low':100,'close':100},
    ]
    result=MultiPositionBacktester(risk_pct=0.5).run(rows,lambda r: {'action':'LONG','stop_distance':1,'rr':2})
    assert not [e for e in result.trades if e.get('event')=='OPEN']


def test_signal_close_executes_on_next_candle_open():
    rows=[
        {'timestamp':'2026-01-01T00:00:00+00:00','symbol':'AAA','open':100,'high':100,'low':100,'close':100},
        {'timestamp':'2026-01-01T00:01:00+00:00','symbol':'AAA','open':100,'high':101,'low':99,'close':100},
        {'timestamp':'2026-01-01T00:02:00+00:00','symbol':'AAA','open':110,'high':111,'low':110,'close':110},
        {'timestamp':'2026-01-01T00:03:00+00:00','symbol':'AAA','open':120,'high':120,'low':120,'close':120},
    ]
    def signal(row):
        if row['timestamp'].endswith('00:00:00+00:00'):
            return {'action':'LONG','stop_distance':5,'rr':10}
        if row['timestamp'].endswith('00:02:00+00:00'):
            return {'action':'CLOSE'}
        return {'action':'WAIT'}
    result=MultiPositionBacktester(risk_pct=0.5, slippage_pct=0).run(rows,signal)
    closes=[e for e in result.trades if e.get('event')=='CLOSE']
    assert closes[0]['reason']=='SIGNAL'
    assert closes[0]['timestamp']=='2026-01-01T00:03:00+00:00'
    assert closes[0]['price']==120


def test_intrabar_stop_closes_without_close_crossing_stop():
    rows=[
        {'timestamp':'2026-01-01T00:00:00+00:00','symbol':'AAA','open':100,'close':100,'high':100,'low':100},
        {'timestamp':'2026-01-01T00:01:00+00:00','symbol':'AAA','open':100,'close':100,'high':101,'low':98},
    ]
    result=MultiPositionBacktester(risk_pct=0.5).run(rows,lambda r: {'action':'LONG','stop_distance':1,'rr':2} if r['timestamp'].endswith('00:00:00+00:00') else {'action':'WAIT'})
    closes=[e for e in result.trades if e.get('event')=='CLOSE']
    assert closes and closes[0]['reason']=='SL'


def test_both_stop_and_target_is_conservative_stop():
    rows=[
        {'timestamp':'2026-01-01T00:00:00+00:00','symbol':'AAA','open':100,'close':100,'high':100,'low':100},
        {'timestamp':'2026-01-01T00:01:00+00:00','symbol':'AAA','open':100,'close':100,'high':102,'low':98},
    ]
    result=MultiPositionBacktester(risk_pct=0.5).run(rows,lambda r: {'action':'LONG','stop_distance':1,'rr':1} if r['timestamp'].endswith('00:00:00+00:00') else {'action':'WAIT'})
    closes=[e for e in result.trades if e.get('event')=='CLOSE']
    assert closes and closes[0]['reason']=='SL'


def test_gap_through_long_stop_executes_at_open():
    rows=[
        {'timestamp':'2026-01-01T00:00:00+00:00','symbol':'AAA','open':100,'high':100,'low':100,'close':100},
        {'timestamp':'2026-01-01T00:01:00+00:00','symbol':'AAA','open':100,'high':101,'low':99,'close':100},
        {'timestamp':'2026-01-01T00:02:00+00:00','symbol':'AAA','open':95,'high':96,'low':94,'close':95},
    ]
    result=MultiPositionBacktester(risk_pct=0.5, slippage_pct=0).run(rows,lambda r: {'action':'LONG','stop_distance':2,'rr':2} if r['timestamp'].endswith('00:00:00+00:00') else {'action':'WAIT'})
    closes=[e for e in result.trades if e.get('event')=='CLOSE']
    assert closes[0]['reason']=='SL'
    assert closes[0]['price']==95


def test_gap_through_short_target_executes_at_open():
    rows=[
        {'timestamp':'2026-01-01T00:00:00+00:00','symbol':'AAA','open':100,'high':100,'low':100,'close':100},
        {'timestamp':'2026-01-01T00:01:00+00:00','symbol':'AAA','open':100,'high':101,'low':99,'close':100},
        {'timestamp':'2026-01-01T00:02:00+00:00','symbol':'AAA','open':95,'high':96,'low':94,'close':95},
    ]
    result=MultiPositionBacktester(risk_pct=0.5, slippage_pct=0).run(rows,lambda r: {'action':'SHORT','stop_distance':10,'rr':0.4} if r['timestamp'].endswith('00:00:00+00:00') else {'action':'WAIT'})
    closes=[e for e in result.trades if e.get('event')=='CLOSE']
    assert closes[0]['reason']=='TP'
    assert closes[0]['price']==95


def test_candle_open_must_be_inside_high_low():
    rows=[
        {'timestamp':'2026-01-01T00:00:00+00:00','symbol':'AAA','open':105,'high':100,'low':99,'close':100},
    ]
    try:
        MultiPositionBacktester().run(rows,lambda r: {'action':'WAIT'})
    except ValueError as exc:
        assert 'invalid candle OHLC' in str(exc)
    else:
        raise AssertionError('invalid OHLC candle was accepted')
