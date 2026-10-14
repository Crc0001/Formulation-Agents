import math,copy
from pathlib import Path
import pytest
from virtual_reactor_api.native_starch_pair import coordinates,execute,interpolate
ROOT=Path(__file__).resolve().parents[1]
def fixture():
 a=[{'id':'a','name':'API','role':'api','amount_mg':.5},{'id':'s','name':'特白玉米淀粉','role':'excipient','amount_mg':8.5},{'id':'l','name':'乳糖','role':'excipient','amount_mg':51.8},{'id':'m','name':'MCC','role':'excipient','amount_mg':29},{'id':'c','name':'CaSt','role':'excipient','amount_mg':.2}]
 b={'id':'base','ingredients':a};v={'id':'v','baseline_id':'base','ingredients':copy.deepcopy(a)}
 v['ingredients'][1]['amount_mg']=17;v['ingredients'][2]['amount_mg']=43.3
 return b,v

def test_pair_scope_and_no_silent_migration():
 b,v=fixture();x=coordinates(b,v)
 assert x['pair_total_mg']==60.3
 assert x['x_after']==pytest.approx(28.19237147595)
 out=execute(ROOT,b,v,[])
 assert out['target_curves'] is None and len(out['source_curves'])==4
 assert out['consistency'][-1]['difference_min']==pytest.approx(math.log(2)/.110-6.902)
 assert len(out['holdout'])==4
 assert [r['domain'] for r in out['holdout']].count('interpolation')==2
 for mutate in [lambda v:v['ingredients'][3].update(amount_mg=28),lambda v:v['ingredients'][1].update(brand='new'),lambda v:v['ingredients'][1].update(name='预胶化淀粉')]:
  vv=copy.deepcopy(v);mutate(vv);assert coordinates(b,vv) is None

def test_interpolation_limits_and_actual_nodes():
 b,v=fixture();out=execute(ROOT,b,v,[]);rows=out['source']['rows']
 for r in rows:assert interpolate(rows,r['starch_pair_pct'])==pytest.approx(r['k_min_inv'])
 assert interpolate(rows,25)==pytest.approx(math.sqrt(.095*.124))
 for x in [-1,41,float('nan')]:
  with pytest.raises(ValueError):interpolate(rows,x)
 for h in out['holdout']:
  assert h['error_pct']==pytest.approx(100*(h['pred_k']/h['observed_k']-1))
