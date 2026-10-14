import copy
from virtual_reactor_api.topic_data_package import freeze,citation_ids

def test_freeze_independent_and_delta():
 b={'id':'b','ingredients':[]};t={'kind':'pair'};e=[{'id':'e','text':'first'}]
 p=freeze(b,t,e);p['id']='p';e[0]['text']='changed'
 assert p['items'][0]['snapshot']['text']=='first'
 q=freeze(b,t,e+[{'id':'new','text':'new'}],p)
 assert q['added_ids']==['new'] and q['changed_ids']==['e']
 assert freeze(b,t,[],p)['missing_ids']==['e']
 assert citation_ids({'a':[{'source_ids':['e'],'calculation_ids':['c']}],'text':'unlinked'})=={'e','c'}

def test_live_archive_and_frozen_inputs(tmp_path):
 from fastapi.testclient import TestClient
 from virtual_reactor_api.dual_main import create_app
 from virtual_reactor_api.capsule_store import Store
 from virtual_reactor_api.capsule_models import EvidenceInput
 from test_agent_split import base
 async def runner(store,rid,root):
  pid=store.run(rid)['project_id']
  e=store.add_evidence(pid,EvidenceInput(section='comparison',title='new original',text='original data',basis='source',access='page_text',source_url='https://example.org/paper',locator='table 1',applicability='test'),rid)
  # Check inside the runner, before completion: not deferred until task end.
  assert any(x['id']==e['id'] for x in Store(root/'data/organize.sqlite3').rows('evidence',pid))
  store.add_evidence(pid,EvidenceInput(section='comparison',title='calculation',text='not raw',basis='hypothesis',access='imported',applicability='test'),rid)
  store.finish(rid,'partial',report={'summary':'test','findings':[],'gaps':[]})
 with TestClient(create_app(tmp_path,runner)) as c:
  pid=c.post('/api/projects',json={'name':'test','api':'API','market':'China','strength':'1mg','strength_basis':'active'}).json()['id']
  store=Store(tmp_path/'data/origin.sqlite3')
  e=store.add_evidence(pid,EvidenceInput(section='formulation',title='base source',text='data',basis='source',access='page_text',source_url='https://example.org/base',locator='table 1',applicability='test'))
  b=c.post(f'/api/projects/{pid}/baselines',json=dict(title='base',ingredients=base()['ingredients'],process='fixed',api_particle='unknown',mass_basis='mg',source_ids=[e['id']],rationale='test')).json()
  body={'question':'test','baseline_id':b['id'],'research_target':{'kind':'pair','material_ids':['l','s'],'objective':'乳糖淀粉专题'}}
  r=c.post(f'/api/projects/{pid}/interaction/runs',json=body);assert r.status_code==200
  rid=r.json()['id'];url=f'/api/projects/{pid}/topic-data'
  data=c.get(url).json();p=data['packages'][0]
  frozen=c.get(url+'/'+p['id']).json()
  assert p['run_id']==rid and not any(x['title']=='new original' for x in p['items'])
  assert any(x['status']=='archived' for x in data['receipts'])
  assert any(x['status']=='indexed' for x in data['receipts'])
  assert not any(x['title']=='calculation' for x in Store(tmp_path/'data/organize.sqlite3').rows('evidence',pid))
  r=c.post(f'/api/projects/{pid}/interaction/runs',json={**body,'continue_from_run_id':rid});assert r.status_code==200
  assert c.get(url).json()['packages'][-1]['previous_package_id']==p['id']
  assert c.get(url+'/'+p['id']).json()==frozen
  other=c.post('/api/projects',json={'name':'other','api':'API','market':'China','strength':'1mg','strength_basis':'active'}).json()['id']
  assert c.get(f'/api/projects/{other}/topic-data/{p["id"]}').status_code==404
