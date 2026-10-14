import time
from fastapi.testclient import TestClient
from virtual_reactor_api.dual_main import create_app

def test_auto_model_frozen_and_error_stops_sequence(tmp_path,monkeypatch):
 import virtual_reactor_api.model_profiles as mp
 captured=[]
 def resolve(root,pid):
  if pid not in ('astra','glm'):raise ValueError('请选择已有模型')
  return dict(profile_id=pid,label=pid,model='openai:gpt-6-astra',api_key='test-only',base_url='https://example.invalid')
 monkeypatch.setattr(mp,'resolve',resolve)
 async def runner(store,rid,root):
  captured.append(mp.selected_generator.get()['profile_id'])
  store.finish(rid,'partial',error='步骤上限',report={'summary':'saved','findings':[],'gaps':[],'formulations':[]})
 with TestClient(create_app(tmp_path,runner=runner)) as c:
  p=c.post('/api/projects',json={'name':'model route','api':'test','market':'中国','strength':'1mg','strength_basis':'活性成分'}).json()
  assert c.post('/api/projects/'+p['id']+'/origin-autostart?model_profile=invalid').status_code==400
  assert c.post('/api/projects/'+p['id']+'/origin-autostart?model_profile=astra').status_code==200
  for _ in range(50):
   if captured and not c.get('/api/projects/'+p['id']+'/origin-autostart').json()['running']:break
   time.sleep(.02)
  assert captured==['astra']
  assert len(c.get('/api/projects/'+p['id']).json()['origin']['runs'])==1
