import asyncio,json
from types import SimpleNamespace
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from virtual_reactor_api.model_profiles import resolve,public_profiles,using_profile,selected_generator
from virtual_reactor_api.dual_main import create_app

def profiles(root):
 (root/'config').mkdir()
 for name,model,key in [('astra.local.toml','openai:gpt-6-astra','SECRET_A'),('glm.local.toml','anthropic:glm-5.2','SECRET_B')]:
  (root/'config'/name).write_text('[generator]\nmodel="'+model+'"\napi_key="'+key+'"\nbase_url="https://example.org/v1"\n')

def test_public_list_never_exposes_keys(tmp_path):
 profiles(tmp_path)
 result=json.dumps(public_profiles(tmp_path))
 assert 'SECRET' not in result and 'base_url' not in result
 assert all(x['configured'] for x in public_profiles(tmp_path))
 with pytest.raises(ValueError):resolve(tmp_path,'../../bad')

def test_concurrent_selection_is_isolated(tmp_path):
 profiles(tmp_path)
 async def check(pid):
  with using_profile(resolve(tmp_path,pid)):
   await asyncio.sleep(.01)
   assert selected_generator.get()['profile_id']==pid
  assert selected_generator.get() is None
 async def main():await asyncio.gather(check('astra'),check('glm'))
 asyncio.run(main())

def test_api_passes_selected_model_and_saves_only_identity(tmp_path):
 profiles(tmp_path);seen=[]
 async def runner(store,rid,root):
  seen.append(selected_generator.get()['model']);store.finish(rid,'completed')
 with TestClient(create_app(tmp_path,runner=runner)) as c:
  pid=c.post('/api/projects',json={'name':'Model test','api':'TEST','market':'中国','strength':'5mg','strength_basis':'活性成分'}).json()['id']
  assert c.post(f'/api/projects/{pid}/origin/runs',json={'question':'test','model_profile':'invalid'}).status_code==422
  r=c.post(f'/api/projects/{pid}/origin/runs',json={'question':'test','model_profile':'glm'})
  assert r.status_code==200
  snap=c.get('/api/projects/'+pid).json();entry=snap['model_runs'][0]
  assert entry['run_id']==r.json()['id'] and entry['model']=='anthropic:glm-5.2'
  assert 'SECRET' not in json.dumps(snap)
  assert seen==['anthropic:glm-5.2']
