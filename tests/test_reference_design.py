import json
from pathlib import Path
import numpy as np
import pytest
from virtual_reactor_api.reference_design import analyze

def data():
 return {'times':[5,10,15],'factor_names':['A','B'],'unit':'%','trials':[{'batch':str((a,b)),'factors':[a,b],'q':[10+a+b,30+2*a+b,60+a+2*b]} for a in [2,3,5] for b in [2,4,6]],'references':[{'id':'ref','q':[17,40,71]}],'comparability':'unknown','constraints':'sum','source':{}}
def test_target_and_holdout():
 r=analyze(data(),'ref');assert r['selected']['loo_rmse']<1e-10
 assert r['candidate']['rmse_to_reference']<0.1
 assert '不能确认' in r['status'];assert len(r['observed_ranking'])==9
 assert r['observed_ranking'][0]['rmse_to_reference']<=r['observed_ranking'][-1]['rmse_to_reference']
def test_reject_nonfinite_and_incomplete():
 d=data();d['trials'][0]['q'][0]=float('nan')
 with pytest.raises(ValueError):analyze(d,'ref')
 d=data();d['trials'].pop()
 with pytest.raises(ValueError):analyze(d,'ref')


def test_all_reference_batches_are_used():
 d=data();d['references']=[{'id':'a','group':'all','medium':'water','method':'basket','locator':'table','q':[17,40,71]},{'id':'b','group':'all','medium':'water','method':'basket','locator':'table','q':[27,50,81]}]
 r=analyze(d,'all')
 assert len(r['reference_members'])==2
 for row in r['observed_ranking']:
  expected=max(float(np.sqrt(np.mean((np.array(row['q'])-np.array(ref['q']))**2))) for ref in d['references'])
  assert row['rmse_to_reference']==pytest.approx(expected)
 assert len(r['guidance']['next_experiments'])==3
 assert '不能确认' in r['status']
