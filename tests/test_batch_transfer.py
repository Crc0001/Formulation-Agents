import io,json,zipfile
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from virtual_reactor_api.batch_transfer import BatchTransfer,install_routes,digest
from virtual_reactor_api.capsule_store import Store
from virtual_reactor_api.capsule_models import ProjectInput,EvidenceInput
class Queue:
 def load(self,batch):return {'items':[]}
def make(root):return BatchTransfer(root,{k:Store(root/'data'/f'{k}.sqlite3') for k in ('origin','organize','interaction','excipient')},Queue())
def seed(t):
 p=t.store.create_project(ProjectInput(name='第108批原研库 · 测试 · 108-1',api='API',market='JP',strength='5mg',strength_basis='active'))
 r=t.store.create_run(p['id'],'研究来源')
 b=b'original document';h=digest(b);d=t.root/'data/documents';d.mkdir();(d/h).write_bytes(b)
 e=t.store.add_evidence(p['id'],EvidenceInput(section='reference',title='原文',text='正文',basis='source',source_url='https://example.org/source',locator='p1',applicability='来源',fields={'sha256':h}),run_id=r['id'])
 return p,r,e,h
def test_roundtrip_and_duplicate(tmp_path):
 a=make(tmp_path/'a');p,r,e,h=seed(a);b=make(tmp_path/'b');data=a.export(108);preview=b.preview(data);assert preview['active']==1 and preview['files']==1
 result=b.apply(preview['token']);pid=result['projects'][0]['id'];s=b.store.snapshot(pid)
 assert s.runs[0].status=='partial' and s.evidence[0].run_id==s.runs[0].id
 assert (b.root/'data/documents'/h).read_bytes()==b'original document'
 assert all(st.project(pid)['name']==p['name'] for st in b.stores.values())
 assert b.apply(preview['token'])['duplicate']
 new=b.apply(b.preview(a.export(108))['token']);assert new['added_records']==0
 assert len(b.store.rows('runs',pid))==1
 assert not list((b.root/'data').glob('origin-batch-jobs/*'))
def test_local_history_preserved(tmp_path):
 a=make(tmp_path/'a');p,r,e,h=seed(a);data=a.export(108)
 with a.store.db() as c:
  changed={**e,'text':'本机修订'};c.execute('update evidence set payload=? where id=?',(json.dumps(changed),e['id']))
 result=a.apply(a.preview(data)['token']);rows=a.store.rows('evidence',p['id'])
 assert {x['text'] for x in rows}=={'正文','本机修订'}
 assert a.store.run(r['id'])['status']=='queued'
def test_missing_and_secret(tmp_path):
 a=make(tmp_path);p,r,e,h=seed(a);(a.root/'data/documents'/h).unlink()
 with a.store.db() as c:
  e['text']='credential sk-'+('x'*24);c.execute('update evidence set payload=? where id=?',(json.dumps(e),e['id']))
 m,_=a.read(a.export(108));assert m['missing_files']==[h];assert 'sk-' not in json.dumps(m)
@pytest.mark.parametrize('kind',['path','hash','duplicate'])
def test_bad_zip(tmp_path,kind):
 a=make(tmp_path);p,r,e,h=seed(a);data=a.export(108)
 src=zipfile.ZipFile(io.BytesIO(data));out=io.BytesIO()
 with zipfile.ZipFile(out,'w') as z:
  for n in src.namelist():
   v=src.read(n)
   if kind=='hash' and n.startswith('documents/'):v=b'corrupted'
   if kind=='duplicate' and n=='manifest.json':
    m=json.loads(v);m['projects'].append(m['projects'][0]);v=json.dumps(m).encode()
   z.writestr(n,v)
  if kind=='path':z.writestr('../escape',b'bad')
 with pytest.raises(ValueError):a.preview(out.getvalue())
def test_http(tmp_path):
 a=make(tmp_path);seed(a);app=FastAPI();install_routes(app,a)
 with TestClient(app) as c:
  assert c.get('/api/origin-registry/batches/108/export-preview').json()['products']==1
  zipdata=c.get('/api/origin-registry/batches/108/export');assert zipdata.status_code==200
  preview=c.post('/api/origin-registry/import-preview',content=zipdata.content).json()
  result=c.post('/api/origin-registry/import/'+preview['token']);assert result.status_code==200
  assert c.get('/api/origin-registry/imports').json()[0]['batch']==108
  assert c.post('/api/origin-registry/import-preview',content=b'bad').status_code==422
