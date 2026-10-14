import math,pytest
from virtual_reactor_api.source_curve_models import fit_curve,calculate_and_save

def test_known_weibull_and_holdout():
    points=[[t,92*(1-math.exp(-(t/8)**1.4))] for t in [0,2,4,8,12,20,30]]
    r=fit_curve(points);m=r['models'][1]
    assert m['rmse_pp']<1e-5
    assert abs(m['parameters']['Qinf_percent']-92)<1e-3
    assert abs(m['internal_last_point_check']['predicted']-points[-1][1])<1e-3
    assert r['observed_points']==points

def test_bad_data():
    for p in [[[1,2]]*6,[[0,0],[1,2],[2,4]],[[i,float('nan')] for i in range(6)]]:
        with pytest.raises(ValueError):fit_curve(p)

def test_source_gate():
    class Store:
        def run(self,r):return {'project_id':'p'}
        def rows(self,*args):return []
        def add_evidence(self,*args):raise AssertionError('must not save')
    with pytest.raises(ValueError,match='原文'):
        calculate_and_save(Store(),'p','r',dict(title='test',conditions='test',change='test',confounders='unknown',arms=[{},{}]))


def test_paired_relationship_does_not_interpolate():
 from virtual_reactor_api.source_curve_models import paired_relation
 r=paired_relation([{'observed_points':[[5,40],[10,80],[30,99]]},{'observed_points':[[5,50],[10,70],[20,98]]}])
 assert r['observed_direction']=='mixed'
 assert [p['delta_pp'] for p in r['matched_time_differences']]==[10,-10]
 assert [p['time_min'] for p in r['matched_time_differences']]==[5,10]


def test_adjacent_units_without_identifier_leak():
 from virtual_reactor_api.source_curve_models import dissolution_numbers
 n=dissolution_numbers('F5 CN123 5min 10分钟 35.7% 100.5％')
 assert n==[5,10,35.7,100.5]

def test_separate_header_and_row_keep_provenance():
 from virtual_reactor_api.source_curve_models import point_quote_numbers
 header='Time Minute -3 Minute -5 Minute -7'
 row='F1 99.13 100.80 101.34'
 p=dict(quote=row,time_quote=header,time_locator='Table9 header',value_locator='Table9 F1')
 times,values=point_quote_numbers(p,header+'\n'+row)
 assert times==[3,5,7] and values==[99.13,100.80,101.34]
 with pytest.raises(ValueError):point_quote_numbers(p,row)
 with pytest.raises(ValueError):point_quote_numbers({**p,'value_locator':''},header+'\n'+row)
