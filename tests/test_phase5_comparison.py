from research.run_phase5_comparison import variants,filtered_signal

def test_four_controlled_variants_exist():
    assert variants()==('C_BASELINE','C_ASSET','C_ENTRY','C_BOTH')

def test_baseline_is_untouched():
    s={'action':'LONG','diagnostics':{}}
    assert filtered_signal(s,{},0,'C_BASELINE') is s

def test_asset_filter_can_block_variant():
    s={'action':'LONG','diagnostics':{}}
    out=filtered_signal(s,{'atr_pct':.01,'vol_ratio':1},100,'C_ASSET')
    assert out['action']=='WAIT'
