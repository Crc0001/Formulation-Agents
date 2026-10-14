import pytest
from virtual_reactor_api.doe_model_package import package,evaluate

def model():
 return {'kind':'source_response_model_json','record':{'domain':[0,10],'center':5,'scale':10,'selected_degree':2,'models':[{'degree':2,'coefficients':[4,2,3],'rmse':.1}],'x_unit':'mg','y_unit':'N'}}
def test_saved_coefficients_and_domain():
 r=evaluate(model(),[0,5,10]);assert r['points']==[[0,3.75],[5,4],[10,5.75]]
 assert r['change']==2 and r['target_prediction'] is None
 for values in [[-1,5],[0,11],[0,float('nan')],[5]]:
  with pytest.raises(ValueError):evaluate(model(),values)
 with pytest.raises(ValueError):evaluate({'kind':'source_curve_model_json'},[0,10])
def test_exact_report_references_only():
 import json
 e={'id':'a','title':'test','fields':{'source_response_model_json':json.dumps(model()['record'])}}
 b={'baseline_id':'base','research_target':{'material_ids':['x']}}
 run={'id':'run','report':{'interaction_research':{'studies':[{'calculation_ids':['a']}]}}}
 p=package(b,run,[e,{**e,'id':'unrelated'}]);assert len(p['models'])==1
 old=p['version'];e['fields']['source_response_model_json']='{}'
 assert package(b,run,[e])['version']!=old
 assert p['models'][0]['record']['domain']==[0,10]

def test_api_application_and_isolation(tmp_path):
 import json,sqlite3,threading
 from fastapi.testclient import TestClient
 from virtual_reactor_api.dual_main import create_app
 from virtual_reactor_api.capsule_store import Store
 from virtual_reactor_api.capsule_models import EvidenceInput
 from test_agent_split import base
 from test_dual import variant
 seen=[];done=threading.Event()
 async def runner(store,rid,root):
  seen.append(store.run(rid)['message']);store.finish(rid,'completed');done.set()
 with TestClient(create_app(tmp_path,runner)) as c:
  pid=c.post('/api/projects',json={'name':'test','api':'API','market':'China','strength':'1mg','strength_basis':'active'}).json()['id']
  st=Store(tmp_path/'data/origin.sqlite3')
  e=st.add_evidence(pid,EvidenceInput(section='formulation',title='test',text='test',basis='source',access='page_text',source_url='https://example.org',locator='table',applicability='test'))
  b=c.post(f'/api/projects/{pid}/baselines',json=dict(title='base',ingredients=base()['ingredients'],process='fixed',api_particle='unknown',mass_basis='mg',source_ids=[e['id']],rationale='test')).json()
  v=c.post(f'/api/projects/{pid}/variants',json=variant(b)).json()
  si=Store(tmp_path/'data/interaction.sqlite3');run=si.create_run(pid,'test')
  calc=si.add_evidence(pid,EvidenceInput(section='comparison',title='model',text='software fixture',basis='hypothesis',access='imported',applicability='test',fields={'source_response_model_json':json.dumps(model()['record'])}),run['id'])
  si.finish(run['id'],'completed',report={'summary':'test','findings':[],'gaps':[],'interaction_research':{'studies':[{'calculation_ids':[calc['id']], 'left_id':'l','right_id':'s','evidence_scope':'placebo',**{k:'test' for k in ('conditions','response','observed_relation','mechanism_hypothesis','equation','parameter_basis','applicability')}}]}})
  with sqlite3.connect(tmp_path/'data/workbench.sqlite3') as db:db.execute('INSERT INTO records VALUES(?,?,?,?)',('binding','interaction_runs',pid,json.dumps({'run_id':run['id'],'baseline_id':b['id'],'research_target':{'material_ids':['l','s']}})))
  body={'source_run_id':run['id'],'evidence_id':calc['id'],'variant_id':v['id'],'values':[0,5,10]}
  url=f'/api/projects/{pid}/doe-model-applications'
  a=c.post(url,json=body);assert a.status_code==200,a.text
  assert c.post(url,json=body).json()['id']==a.json()['id']
  assert c.post(url,json={**body,'values':[0,11]}).status_code==422
  assert c.post(url,json={**body,'source_run_id':'wrong'}).status_code==422
  other=c.post('/api/projects',json={'name':'other','api':'API','market':'China','strength':'1mg','strength_basis':'active'}).json()['id']
  assert c.post(f'/api/projects/{other}/doe-model-applications',json=body).status_code==404
  result=c.post(f'/api/projects/{pid}/excipient/runs',json={'variant_id':v['id'],'question':'应用已有模型'})
  assert result.status_code==200 and done.wait(5)
  assert a.json()['id'] in seen[0] and '04已执行来源模型应用' in seen[0]
  assert c.get('/api/projects/'+pid).json()['variants'][0]==v
