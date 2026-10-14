from fastapi.testclient import TestClient
from virtual_reactor_api.dual_main import create_app
from virtual_reactor_api.capsule_store import Store
from virtual_reactor_api.capsule_models import EvidenceInput

def test_source_categories_preserve_records_and_project_isolation(tmp_path):
 with TestClient(create_app(tmp_path)) as client:
  body=dict(name='test',api='API',market='China',strength='1mg',strength_basis='active')
  p=client.post('/api/projects',json=body).json()['id']
  other=client.post('/api/projects',json={**body,'name':'other'}).json()['id']
  store=Store(tmp_path/'data/organize.sqlite3')
  e=store.add_evidence(p,EvidenceInput(section='comparison',title='source',text='Original source data',basis='source',access='page_text',applicability='software test only',locator='table 1',source_url='https://example.org/report'))
  original=store.rows('evidence',p)
  url=f'/api/projects/{p}/data-sources'
  assert client.get(url).json()['sources'][0]['category']=='literature_pending'
  assert client.post(url+'/'+e['id']+'/category',json={'category':'third_party'}).status_code==200
  assert client.get(url).json()['sources'][0]['category']=='third_party'
  assert store.rows('evidence',p)==original
  assert client.post(f'/api/projects/{other}/data-sources/{e["id"]}/category',json={'category':'lab'}).status_code==404
  assert client.post(url+'/'+e['id']+'/category',json={'category':'bad'}).status_code==422
  assert client.post(url+'/'+e['id']+'/category',json={'category':'unclassified'}).status_code==200
  assert client.get(url).json()['sources'][0]['category']=='unclassified'


