import asyncio
from fastapi.testclient import TestClient
from virtual_reactor_api.dual_main import create_app

def test_topic_dispatch_and_running_dedup(tmp_path):
 async def runner(store,rid,root):
  await asyncio.sleep(2)
  store.finish(rid,'completed')
 with TestClient(create_app(tmp_path,runner)) as c:
  pid=c.post('/api/projects',json={'name':'test','api':'test','market':'China','strength':'1mg','strength_basis':'active'}).json()['id']
  endpoint=f'/api/projects/{pid}/topic-research'
  assert c.post(endpoint,json={'materials':['淀粉','淀粉']}).status_code==422
  r=c.post(endpoint,json={'materials':['微粉硅胶','淀粉']});assert r.status_code==200,r.text
  second=c.post(endpoint,json={'materials':['淀粉','微粉硅胶']});assert second.status_code==200,second.text
  assert second.json()['run_id']==r.json()['run_id'] and second.json()['reused']
  topics=c.get('/api/research-topics').json()
  assert len(topics)==1 and topics[0]['materials']==['微粉硅胶','淀粉']
  assert topics[0]['models']==[]
  snap=c.get('/api/projects/'+pid).json()
  assert len(snap['research_cases'])==1 and snap['baselines']==[] and snap['variants']==[]
