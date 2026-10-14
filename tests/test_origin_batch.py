import asyncio,json
from virtual_reactor_api.origin_batch import BatchResearch
from virtual_reactor_api.capsule_store import Store
from virtual_reactor_api.capsule_models import ProjectInput

def setup(tmp_path):
 store=Store(tmp_path/'origin.sqlite3');p=store.create_project(ProjectInput(name='existing',api='drug',market='CN',strength='10mg',strength_basis='label',dosage_form='tablet'))
 calls=[]
 async def submit(pid,q,m):
  calls.append(q)
  return {'id':'r1','status':'queued'}
 q=BatchResearch(tmp_path,None,store,lambda v:store.create_project(v),submit)
 s={'batch':108,'enabled':False,'model_profile':'astra','status':'ready','source':{},'items':[{'name':'drug','project_id':p['id'],'rows':[{'entry_number':'108-1','cells':['108-1','drug','name','10mg','holder','','']}],'phases':[],'status':'排队'}]};q.save(s)
 return q,calls

def test_start_idempotent_and_pause_before_dispatch(tmp_path):
 q,calls=setup(tmp_path)
 async def go():
  await q.start(108,'astra');await q.start(108,'astra');await q.pause(108);await q.tick()
 asyncio.run(go());assert not calls;assert len(q.load(108)['items'])==1

def test_dispatch_is_saved_and_no_extra_submission_in_tick(tmp_path):
 q,calls=setup(tmp_path)
 asyncio.run(q.start(108,'astra'));asyncio.run(q.tick())
 s=q.load(108);assert len(calls)==1;assert s['items'][0]['phases']==[{'phase':1,'run_id':'r1','status':'queued'}]
 assert '【108批整批建档:108-1:阶段1】' in calls[0]

def test_completed_and_blocked_not_restarted(tmp_path):
 q,calls=setup(tmp_path);s=q.load(108);s['items'][0]['status']='三阶段已交付，待逐项验收';q.save(s)
 asyncio.run(q.start(108,'astra'));asyncio.run(q.tick());assert not calls;assert not q.load(108)['enabled']

def test_other_project_running_blocks_dispatch(tmp_path):
 q,calls=setup(tmp_path);pid=q.load(108)['items'][0]['project_id'];r=q.store.create_run(pid,'manual')
 asyncio.run(q.start(108,'astra'));asyncio.run(q.tick());assert not calls
 q.store.finish(r['id'],'completed',report={'summary':'done','findings':[],'gaps':[]})
 asyncio.run(q.tick());assert len(calls)==1


def test_pause_keeps_inflight_then_advances_without_new_run(tmp_path):
 q,calls=setup(tmp_path);s=q.load(108);i=s['items'][0];r=q.store.create_run(i['project_id'],'manual');i.update(status='研究中',phases=[{'phase':1,'run_id':r['id'],'status':'queued'}]);s['enabled']=True;q.save(s)
 from virtual_reactor_api.origin_stages import IDENTITY_ROWS
 asyncio.run(q.pause(108));q.store.finish(r['id'],'partial',report={'summary':'saved','findings':[],'gaps':[],'decision_comparison':{'title':'identity','candidates':['A'],'recommendation':'未知','reasons':[],'limitations':[],'next_steps':[],'rows':[{'metric':name,'values':['未知']} for name in IDENTITY_ROWS]}})
 asyncio.run(q.tick());assert not calls;assert q.load(108)['items'][0]['status']=='排队'


def test_existing_marker_reconciles_after_dispatch_save_crash(tmp_path):
 q,calls=setup(tmp_path);pid=q.load(108)['items'][0]['project_id'];r=q.store.create_run(pid,'【108批整批建档:108-1:阶段1】');q.store.finish(r['id'],'completed',report={'summary':'done','findings':[],'gaps':[]})
 asyncio.run(q.start(108,'astra'));asyncio.run(q.tick());assert not calls
 assert q.load(108)['items'][0]['phases'][0]['run_id']==r['id']


def test_http_controls_preserve_legacy_manifest_and_validate_model_config(tmp_path):
 from fastapi.testclient import TestClient
 from virtual_reactor_api.dual_main import create_app
 d=tmp_path/'reference/origin-batch108-research-test';d.mkdir(parents=True)
 manifest={'batch':108,'status':'ready','items':[{'name':'drug','status':'排队','rows':[],'phases':[]}],'model_profile':'astra'}
 (d/'state.json').write_text(json.dumps(manifest),encoding='utf-8')
 from test_model_profiles import profiles
 profiles(tmp_path)
 c=TestClient(create_app(tmp_path))
 url='/api/origin-registry/batches/108/research'
 assert c.get(url).json()['total']==1
 assert c.post(url+'?model_profile=invalid').status_code==422
 assert c.post(url+'?model_profile=glm').json()['model_profile']=='glm'
 assert c.post(url).json()['enabled']
 assert not c.post(url+'/pause').json()['enabled']
 assert json.loads((d/'state.json').read_text())==manifest

def test_manual_stage_report_reused_without_batch_marker(tmp_path):
 q,calls=setup(tmp_path);pid=q.load(108)['items'][0]['project_id'];r=q.store.create_run(pid,'【原研及处方工艺】【01阶段1】existing manual research');q.store.finish(r['id'],'partial',report={'summary':'done','findings':[],'gaps':[]})
 asyncio.run(q.start(108,'astra'));asyncio.run(q.tick());assert not calls
 assert q.load(108)['items'][0]['phases'][0]['run_id']==r['id']


def test_incomplete_report_does_not_advance(tmp_path):
 q,calls=setup(tmp_path);s=q.load(108);i=s['items'][0];r=q.store.create_run(i['project_id'],'manual');i.update(status='研究中',phases=[{'phase':3,'run_id':r['id'],'status':'queued'}]);q.save(s)
 q.store.finish(r['id'],'partial',report={'summary':'正在逐段整理归档来源','findings':[],'gaps':['候选比较尚未完成（ValidationError）']})
 asyncio.run(q.tick());item=q.load(108)['items'][0]
 assert item['status']=='中断待核' and item['phases'][0]['delivery_issues'] and not calls
