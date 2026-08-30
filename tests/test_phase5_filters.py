from research.phase5_filters import asset_quality,entry_quality

def test_asset_quality_rejects_insufficient_history():
    ok,reason=asset_quality({'atr_pct':.01,'vol_ratio':1},249)
    assert not ok and reason=='insufficient_history'

def test_asset_quality_rejects_extreme_volatility():
    ok,reason=asset_quality({'atr_pct':.20,'vol_ratio':1},500)
    assert not ok and reason=='too_high_volatility'

def test_entry_quality_requires_independent_confirmations():
    d={'trend':True,'medium_momentum':True,'short_momentum':True,'microstructure':True,'bounce_checks':{'pullback_touch':True,'ema_reclaim':True,'directional_followthrough':True,'pullback_structure':False}}
    assert entry_quality(d,'LONG')[0]

def test_entry_quality_rejects_weak_bounce():
    d={'trend':True,'medium_momentum':True,'short_momentum':True,'microstructure':True,'bounce_checks':{'pullback_touch':True,'ema_reclaim':False,'directional_followthrough':False,'pullback_structure':False}}
    assert not entry_quality(d,'LONG')[0]
