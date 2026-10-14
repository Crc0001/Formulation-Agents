import math
import pytest
from fastapi.testclient import TestClient
from virtual_reactor_api.dual_main import create_app,Ingredient,VariantInput,check_variant,fit,curve
from virtual_reactor_api.capsule_models import EvidenceInput
from virtual_reactor_api.capsule_store import Store

@pytest.fixture
def setup(tmp_path):
 app=create_app(tmp_path,runner=lambda *args:None)
 with TestClient(app) as c:
  p=c.post('/api/projects',json={'name':'隔离测试','api':'API','market':'中国','strength':'5mg','strength_basis':'活性成分'}).json();pid=p['id']
  e=Store(tmp_path/'data/origin.sqlite3').add_evidence(pid,EvidenceInput(section='formulation',title='软件测试证据',text='TEST ONLY',basis='source',source_url='https://example.org/test',locator='test',applicability='仅软件测试',access='full_text'))
  ingredients=[{'id':'api','name':'API','role':'api','amount_mg':5},{'id':'lactose','name':'乳糖','role':'excipient','amount_mg':95}]
  b=c.post(f'/api/projects/{pid}/baselines',json={'title':'测试基准','ingredients':ingredients,'process':'锁定直混','api_particle':'实测依据测试字段','mass_basis':'mg/粒','source_ids':[e['id']],'rationale':'仅软件测试'}).json()
  yield c,pid,b

def variant(b,**kw):return {'baseline_id':b['id'],'title':'V','ingredients':b['ingredients'],'method':'pH6.8 900mL paddle 50rpm 37C',**kw}

def test_dissolution_binding_is_additive_and_idempotent(setup):
 c,pid,b=setup
 value={'baseline_id':b['id'],'source_id':b['source_ids'][0],'sample':'example1','locator':'table1','binding_note':'reviewed source formula and process','medium':'water','volume_ml':900,'rpm':50,'apparatus':'paddle','points':[[5,3.5],[10,15.4],[15,29.7],[30,61.4]]}
 first=c.post(f'/api/projects/{pid}/dissolution-profiles',json=value)
 assert first.status_code==200
 assert c.post(f'/api/projects/{pid}/dissolution-profiles',json=value).json()['id']==first.json()['id']
 snap=c.get('/api/projects/'+pid).json()
 assert snap['baselines'][0]==b and len(snap['dissolution_profiles'])==1
 assert c.post(f'/api/projects/{pid}/dissolution-profiles',json={**value,'source_id':'wrong'}).status_code==422
 assert c.post(f'/api/projects/{pid}/release-models',json={'profile_id':'wrong'}).status_code==404

def test_independent_handoff_and_immutable_versions(setup):
 c,pid,b=setup;s=c.get('/api/projects/'+pid).json()
 assert len(s['origin']['evidence'])==len(s['excipient']['evidence'])==1
 assert len(s['baselines'])==1 and s['baselines'][0]['version']==1
 assert c.post(f'/api/projects/{pid}/variants',json=variant(b)).status_code==200
 assert c.get('/api/projects/'+pid).json()['baselines'][0]==b

def test_kind_api_and_total_guard(setup):
 c,pid,b=setup
 for ingredients in [b['ingredients'][:1],[{**b['ingredients'][0],'amount_mg':6},b['ingredients'][1]],[b['ingredients'][0],{**b['ingredients'][1],'name':'淀粉'}],[b['ingredients'][0],{**b['ingredients'][1],'amount_mg':0}],[b['ingredients'][0],{**b['ingredients'][1],'amount_mg':94}]]:
  assert c.post(f'/api/projects/{pid}/variants',json=variant(b,ingredients=ingredients)).status_code==422
 good=[b['ingredients'][0],{**b['ingredients'][1],'brand':'品牌B','grade':'细粒'}]
 assert c.post(f'/api/projects/{pid}/variants',json=variant(b,ingredients=good)).status_code==200

def test_anchor_fits_known_curve_but_rejects_other_variant_and_method(setup):
 c,pid,b=setup;v=c.post(f'/api/projects/{pid}/variants',json=variant(b)).json();v2=c.post(f'/api/projects/{pid}/variants',json=variant(b,title='V2')).json()
 sim=c.post(f'/api/projects/{pid}/simulations',json={'variant_id':v['id'],'tau_min':20,'beta':1.2,'basis':'explicit_hypothesis','source':'软件测试假设，不属于药学结果'}).json()
 points=[[t,100*(1-math.exp(-(t/25)**1.4))] for t in [5,10,20,30,45]]
 data={'variant_id':v['id'],'prediction_id':sim['id'],'batch':'测试批','method':v['method'],'points':points}
 a=c.post(f'/api/projects/{pid}/anchors',json=data);assert a.status_code==200
 assert abs(a.json()['tau_min']-25)<1e-8 and a.json()['fit_rmse_pp']<1e-8
 assert a.json()['prior_rmse_pp']>0
 assert c.post(f'/api/projects/{pid}/anchors',json={**data,'variant_id':v2['id']}).status_code==422
 assert c.post(f'/api/projects/{pid}/anchors',json={**data,'method':'different'}).status_code==422
 assert len(c.get('/api/projects/'+pid).json()['anchors'])==1

def test_curve_limits_and_insufficient_anchor():
 assert curve(20,1.2)[0][1]==0
 q=[x[1] for x in curve(20,1.2)];assert all(0<=x<=100 for x in q) and q==sorted(q)
 from virtual_reactor_api.dual_main import AnchorInput
 from pydantic import ValidationError
 assert AnchorInput(variant_id='v',batch='x',method='x',points=[[1,110]]).points[0][1]==110

def test_external_connector_quarantine(setup):
 c,pid,b=setup
 assert c.get('/api/integrations/excipient/schema').status_code==200
 data={'name':'乳糖','manufacturer':'测试','grade':'x','specification':'粒径测法待核','source_url':'https://example.org/spec','locator':'test','limitations':'测试条目'}
 r=c.post('/api/catalog/excipient',json=data);assert r.status_code==200 and r.json()['status']=='外部导入待核验'
 assert len(c.get('/api/catalog/origin').json())==0
 assert c.get('/api/projects/'+pid).json()['variants']==[]


def test_raw_out_of_range_is_saved_without_clipping_or_false_calibration(setup):
 c,pid,b=setup;v=c.post(f'/api/projects/{pid}/variants',json=variant(b)).json()
 raw=[[5,20],[10,65],[20,103]]
 r=c.post(f'/api/projects/{pid}/anchors',json={'variant_id':v['id'],'batch':'raw','method':v['method'],'points':raw})
 assert r.status_code==200 and r.json()['points']==raw and r.json()['points_fitted']==[]
 assert r.json()['fit_rmse_pp'] is None

def test_numeric_extremes_stay_finite():
 assert curve(1e-300,10)[-1][1]==100
 assert curve(1e300,10)[-1][1]>=0

def test_excipient_dispatch_keeps_frozen_baseline(tmp_path):
 import threading
 done=threading.Event()
 seen=[]
 async def runner(store,rid,root):
  seen.append(store.run(rid)['message'])
  store.finish(rid,'completed')
  done.set()
 with TestClient(create_app(tmp_path,runner=runner)) as c:
  pid=c.post('/api/projects',json={'name':'隔离交接测试','api':'诺氟沙星','market':'中国','strength':'200mg','strength_basis':'标示量'}).json()['id']
  e=Store(tmp_path/'data/origin.sqlite3').add_evidence(pid,EvidenceInput(section='formulation',title='软件测试',text='TEST ONLY',basis='source',source_url='https://example.org/test',locator='test',applicability='仅软件测试',access='full_text'))
  data={'title':'隔离测试基准','ingredients':[{'id':'a','name':'诺氟沙星','role':'api','amount_mg':98},{'id':'b','name':'硬脂酸镁','role':'excipient','amount_mg':1.4}], 'process':'测试条件','api_particle':'未知','mass_basis':'原料称量，非200mg','source_ids':[e['id']],'rationale':'软件测试'}
  b=c.post(f'/api/projects/{pid}/baselines',json=data);assert b.status_code==200
  base=b.json();v=c.post(f'/api/projects/{pid}/variants',json=variant(base)).json()
  assert c.post(f'/api/projects/{pid}/excipient/runs',json={'question':'测试'}).status_code==422
  r=c.post(f'/api/projects/{pid}/excipient/runs',json={'question':'测试','variant_id':v['id']});assert r.status_code==200
  assert done.wait(3)
  assert seen and '原料称量，非200mg' in seen[0] and '98.0' in seen[0]
  assert c.get('/api/projects/'+pid).json()['baselines'][0]==base

def test_core_scope_handoff_preserves_fixed_outer(setup):
 c,pid,b=setup
 data={k:b[k] for k in ['title','ingredients','process','api_particle','mass_basis','source_ids','rationale']}
 data.update(screening_scope='core_or_fill',fixed_outer_context='HPC + pigment; individual amounts unknown; fixed coating gain 3%')
 r=c.post(f'/api/projects/{pid}/baselines',json=data)
 assert r.status_code==200
 base=r.json()
 v=c.post(f'/api/projects/{pid}/variants',json=variant(base)).json()
 assert v['fixed_outer_context']==data['fixed_outer_context']
 assert v['screening_scope']=='core_or_fill'
 assert c.post(f'/api/projects/{pid}/baselines',json={**data,'fixed_outer_context':''}).status_code==422
 assert c.post(f'/api/projects/{pid}/baselines',json={**data,'screening_scope':'whole_unit'}).status_code==422
 assert c.post(f'/api/projects/{pid}/baselines',json={**data,'ingredients':[{**x,'amount_mg':None} if x['role']=='excipient' else x for x in data['ingredients']]}).status_code==422
 assert c.post(f'/api/projects/{pid}/variants',json={**variant(base),'fixed_outer_context':'changed'}).status_code==422
 assert c.get('/api/projects/'+pid).json()['baselines'][0]==b

def test_numeric_brand_guard(setup):
 from virtual_reactor_api.dual_main import check_brand_inputs
 from fastapi import HTTPException
 c,pid,b=setup
 for brand in ['60.3','17','１７','17 mg']:
  items=[b['ingredients'][0],{**b['ingredients'][1],'brand':brand}]
  assert c.post(f'/api/projects/{pid}/variants',json=variant(b,ingredients=items)).status_code==422
  with pytest.raises(HTTPException):check_brand_inputs(items)
 check_brand_inputs([{**b['ingredients'][1],'brand':'3M'}])
