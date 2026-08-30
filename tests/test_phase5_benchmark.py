from research.phase5_benchmark import filter_signal

def test_filter_signal_keeps_wait():
    s={'action':'WAIT'}
    assert filter_signal(s,{},10)==s

def test_filter_signal_blocks_bad_asset():
    s={'action':'LONG','diagnostics':{'trend':True}}
    out=filter_signal(s,{'atr_pct':.01,'vol_ratio':1},100)
    assert out['action']=='WAIT' and out['filter_reason']=='insufficient_history'

def test_filter_signal_allows_confirmed_signal():
    s={'action':'LONG','diagnostics':{'trend':True,'medium_momentum':True,'short_momentum':True,'microstructure':True,'bounce_checks':{'pullback_touch':True,'ema_reclaim':True,'directional_followthrough':True,'pullback_structure':False}}}
    out=filter_signal(s,{'atr_pct':.01,'vol_ratio':1},500)
    assert out['action']=='LONG'
