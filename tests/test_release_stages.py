import math
import numpy as np
import pytest
from virtual_reactor_api.release_stages import states,fit_profile
from virtual_reactor_api.dual_main import DissolutionInput

def test_mass_balance_and_independent_erlang_solution():
    ts=[0,1,5,20,60];k=.2
    result=states(ts,[k,k,k])
    expected=[100*(1-math.exp(-k*t)*(1+k*t+(k*t)**2/2)) for t in ts]
    assert np.max(np.abs(result.sum(axis=1)-100))<1e-9
    assert np.max(np.abs(result[:,3]-expected))<1e-9
    assert np.all(result>=-1e-9)

def test_rate_permutation_nonidentifiability_and_sensitivity():
    ts=[0,5,10,30,90]
    a=states(ts,[.03,.1,.3])[:,3]
    assert np.allclose(a,states(ts,[.3,.1,.03])[:,3])
    assert np.all(states(ts,[.06,.1,.3])[:,3]>=a-1e-9)
    with pytest.raises(ValueError):states(ts,[0,1,2])

def test_source_fit_and_raw_values_preserved():
    p={'id':'p','baseline_id':'b','points':[[5,3.5],[10,15.4],[15,29.7],[20,38.2],[30,61.4],[45,80.1],[60,86.2],[90,90.5]]}
    result=fit_profile(p)
    assert len(result['trials'])==4 and result['best']['rmse_pp']<10
    assert result['input_profile']==p and result['permutation_difference_pp']<1e-8
    assert len(result['scenarios'])==6

def test_profile_validation_preserves_over_100():
    kwargs=dict(baseline_id='b',source_id='s',sample='example',locator='p9',binding_note='reviewed same formula and process',medium='water',volume_ml=900,rpm=50,apparatus='paddle')
    assert DissolutionInput(**kwargs,points=[[5,99],[10,101.6]]).points[1][1]==101.6
    with pytest.raises(ValueError):DissolutionInput(**kwargs,points=[[5,99],[5,100]])
