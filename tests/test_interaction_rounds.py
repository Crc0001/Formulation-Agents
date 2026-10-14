import asyncio
from virtual_reactor_api.interaction_rounds import run_topic
from virtual_reactor_api.capsule_store import Store
from virtual_reactor_api.capsule_models import ProjectInput

def test_topic_three_rounds_keep_comparison_history(tmp_path):
 s=Store(tmp_path/'test.db');p=s.create_project(ProjectInput(name='test',api='test',market='test',strength='1mg',strength_basis='test'));r=s.create_run(p['id'],'fixed target');records=[];seen=[]
 async def runner(store,rid,root):
  seen.append(store.run(rid)['message'])
  store.finish(rid,'partial',report={'summary':'round '+str(len(seen)),'findings':[],'gaps':[]})
 asyncio.run(run_topic(s,r['id'],tmp_path,runner,records.append,'b',{'materials':[{'id':'a','name':'淀粉'},{'id':'b','name':'乳糖'}],'dosage_context':'片剂'}))
 assert len(records)==3 and 'round 1' in seen[1] and 'round 2' in seen[2]
 assert records[0]['report']['summary']=='round 1'
 assert s.run(r['id'])['report']['summary']=='round 3'
 assert all(x['topic']=='淀粉—乳糖对片剂性能的影响' for x in records)

def test_topic_stops_on_failure(tmp_path):
 s=Store(tmp_path/'test.db');p=s.create_project(ProjectInput(name='test',api='test',market='test',strength='1mg',strength_basis='test'));r=s.create_run(p['id'],'fixed');records=[]
 async def runner(store,rid,root):store.finish(rid,'failed',error='connection failure')
 asyncio.run(run_topic(s,r['id'],tmp_path,runner,records.append,'b',{'materials':[],'dosage_context':'片剂'}))
 assert len(records)==1 and records[0]['error']=='connection failure'

def test_final_preserves_earlier_findings(tmp_path):
 s=Store(tmp_path/'test.db');p=s.create_project(ProjectInput(name='test',api='test',market='test',strength='1mg',strength_basis='test'));r=s.create_run(p['id'],'fixed');records=[]
 async def runner(store,rid,root):
  n=len(records)+1
  store.finish(rid,'partial',report={'summary':str(n),'findings':[dict(section='comparison',title='round'+str(n),text='observation',basis='hypothesis',source_ids=[],applicability='test')],'gaps':[]})
 asyncio.run(run_topic(s,r['id'],tmp_path,runner,records.append,'b',{'materials':[],'dosage_context':'片剂'}))
 assert len(s.run(r['id'])['report']['findings'])==3
 assert len(records[2]['report']['findings'])==1
