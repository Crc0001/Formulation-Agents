from pathlib import Path
import hashlib
from fastapi.testclient import TestClient
from virtual_reactor_api.excipient_properties import import_workbook,library,research_context,observation
from virtual_reactor_api.dual_main import create_app
SOURCE=next((Path(__file__).resolve().parents[1]/'reference/excipient-properties').glob('*.xlsx'))

def test_import_idempotent_and_lossless(tmp_path):
 a=import_workbook(tmp_path,SOURCE);import_workbook(tmp_path,SOURCE)
 d=library(tmp_path)
 assert len(d['imports'])==1 and len(d['materials'])==68
 obs=[o for m in d['materials'] for o in m['observations']]
 assert len(obs)==565 and len({m['name'] for m in d['materials']})==37
 assert all(not o['model_eligible'] for o in obs)
 assert hashlib.sha256((tmp_path/a['archive']).read_bytes()).hexdigest()==a['id']
 bad=next(o for o in obs if o['row']==524)
 assert bad['raw']['U']=='0.2' and any('错配' in f for f in bad['flags'])
 assert next(o for o in obs if o['row']==495)['flags']
 assert observation('sheet',1,{'K':'test','U':'0','V':'mg'})['value']=='0'

def test_context_scopes_identity_and_retains_guards(tmp_path):
 import_workbook(tmp_path,SOURCE)
 assert research_context(tmp_path,[{'name':'预胶化淀粉','role':'excipient'}])==''
 assert research_context(tmp_path,[{'name':'乳糖','role':'api'}])==''
 text=research_context(tmp_path,[{'name':'乳糖','role':'excipient'}])
 assert '80目' in text and '错配' in text and '不是当前处方实测' in text
 assert '硬脂酸镁' not in text

def test_api_and_archive_integrity(tmp_path):
 a=import_workbook(tmp_path,SOURCE)
 with TestClient(create_app(tmp_path)) as c:
  assert len(c.get('/api/excipient-properties').json()['materials'])==68
  response=c.get('/api/excipient-properties/source/'+a['id'])
  assert response.status_code==200 and hashlib.sha256(response.content).hexdigest()==a['id']
  assert c.get('/api/excipient-properties/source/unknown').status_code==404
  (tmp_path/a['archive']).write_bytes(b'corrupt')
  assert c.get('/api/excipient-properties/source/'+a['id']).status_code==409


def test_registered_workbook_is_scoped_idempotent_and_integrity_checked(tmp_path):
 from virtual_reactor_api.capsule_store import Store
 from virtual_reactor_api.capsule_models import ProjectInput
 meta=import_workbook(tmp_path,SOURCE);store=Store(tmp_path/'data/test.sqlite3')
 pid=store.create_project(ProjectInput(name='test',api='test',market='test',strength='1',strength_basis='mg'))['id']
 ingredients=[{'name':'乳糖','role':'excipient'}]
 text=research_context(tmp_path,ingredients,store,pid)
 research_context(tmp_path,ingredients,store,pid)
 es=store.rows('evidence',pid);assert len(es)==1
 assert es[0]['id'] in text and es[0]['basis']=='measurement'
 assert es[0]['fields']['verified_workbook_sha256']==meta['id']
 assert '硬脂酸镁' not in es[0]['text'] and 'false' in es[0]['text']
 (tmp_path/meta['archive']).write_bytes(b'bad')
 text=research_context(tmp_path,ingredients,store,pid)
 assert 'source_id' not in text
