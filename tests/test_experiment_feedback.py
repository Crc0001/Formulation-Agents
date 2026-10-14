import json
from test_dual import setup,variant

def test_return_raw_and_idempotent(setup):
 c,pid,b=setup
 v=c.post(f'/api/projects/{pid}/variants',json=variant(b)).json()
 raw=[[5,20],[10,103]]
 a=c.post(f'/api/projects/{pid}/anchors',json={'variant_id':v['id'],'batch':'batch','method':v['method'],'points':raw}).json()
 snap=c.get('/api/projects/'+pid).json();f=snap['experiment_feedback'][0]
 assert f['anchor_id']==a['id'] and f['observed_points']==raw
 assert f['local_fit']['tau_min'] is None and f['prior_prediction'] is None
 assert c.post(f'/api/projects/{pid}/experiment-feedback/sync',json={}).json()['added']==0
 assert c.get('/api/projects/'+pid).json()['baselines'][0]==b
 other=c.post('/api/projects',json={'name':'other','api':'API','market':'China','strength':'1mg','strength_basis':'active'}).json()['id']
 assert c.get('/api/projects/'+other).json()['experiment_feedback']==[]
 assert c.post(f'/api/projects/{other}/anchors',json={'variant_id':v['id'],'batch':'bad','method':v['method'],'points':raw}).status_code==404

def test_snapshot_keeps_prior():
 from virtual_reactor_api.experiment_feedback import feedback
 a={'id':'a','variant_snapshot':{'id':'v','baseline_id':'b'},'batch':'batch','method':'m','points':[[5,20]],'prior':{'id':'p','tau_min':10}}
 f=feedback(a);a['points'][0][1]=99;a['prior']['tau_min']=100
 assert f['observed_points']==[[5,20]] and f['prior_prediction']['tau_min']==10

def test_03_receives_feedback(tmp_path):
 import threading
 from fastapi.testclient import TestClient
 from virtual_reactor_api.dual_main import create_app
 from virtual_reactor_api.capsule_store import Store
 from virtual_reactor_api.capsule_models import EvidenceInput
 from test_agent_split import base
 done=threading.Event();seen=[]
 async def runner(store,rid,root):
  seen.append(store.run(rid)['message']);store.finish(rid,'completed');done.set()
 with TestClient(create_app(tmp_path,runner)) as c:
  pid=c.post('/api/projects',json={'name':'test','api':'API','market':'China','strength':'1mg','strength_basis':'active'}).json()['id']
  e=Store(tmp_path/'data/origin.sqlite3').add_evidence(pid,EvidenceInput(section='formulation',title='test',text='test',basis='source',access='page_text',source_url='https://example.org',locator='table',applicability='test'))
  b=c.post(f'/api/projects/{pid}/baselines',json=dict(title='base',ingredients=base()['ingredients'],process='fixed',api_particle='unknown',mass_basis='mg',source_ids=[e['id']],rationale='test')).json()
  v=c.post(f'/api/projects/{pid}/variants',json=variant(b)).json()
  a=c.post(f'/api/projects/{pid}/anchors',json={'variant_id':v['id'],'batch':'test-batch','method':v['method'],'points':[[5,20]]}).json()
  r=c.post(f'/api/projects/{pid}/interaction/runs',json={'baseline_id':b['id'],'question':'【接续：汇总】复核实验','research_target':{'kind':'pair','material_ids':['l','s'],'objective':'乳糖淀粉'}})
  assert r.status_code==200 and done.wait(5)
  assert a['id'] in seen[0] and '04实测回传03' in seen[0]
  snap=c.get('/api/projects/'+pid).json()
  assert snap['feedback_uses'][0]['feedback_ids']==[snap['experiment_feedback'][0]['id']]
  assert snap['anchors'][0]==a
