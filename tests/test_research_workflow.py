import json,shutil,time
from pathlib import Path
from fastapi.testclient import TestClient
from virtual_reactor_api.research_workflow import execute_workflow,gate_report,register_case_source
from virtual_reactor_api.dual_main import create_app
from virtual_reactor_api.capsule_store import Store
from virtual_reactor_api.capsule_models import EvidenceInput,ProjectInput

ROOT=Path(__file__).resolve().parents[1]

def test_source_registration_keeps_original_separate_and_reuses_identity(tmp_path):
 path=Path('reference/cross-formulation-validation-20260924')
 shutil.copytree(ROOT/path,tmp_path/path)
 s=Store(tmp_path/'source-test.sqlite3')
 p=s.create_project(ProjectInput(name='test',api='test',market='test',strength='test',strength_basis='test'))
 r=s.create_run(p['id'],'test')
 sid=register_case_source(s,p['id'],r['id'],tmp_path)
 assert register_case_source(s,p['id'],r['id'],tmp_path)==sid
 source=s.rows('evidence',p['id'])[0]
 assert source['basis']=='source' and '957' in source['text']
 assert len(s.rows('evidence',p['id']))==1

def test_recompute_ignores_previously_saved_prediction_and_respects_missing_sources(tmp_path):
 base={'id':'b','ingredients':[{'id':'e','name':'MCC','amount_mg':20}]}
 variant={'id':'v','ingredients':[{'id':'e','name':'MCC','amount_mg':5}]}
 path=Path('reference/cross-formulation-validation-20260924')
 shutil.copytree(ROOT/path,tmp_path/path)
 p=tmp_path/path/'results.json';data=json.loads(p.read_text(encoding='utf-8'))
 data['records']['CPV']['holdout']['pred_t80_min']=999
 p.write_text(json.dumps(data),encoding='utf-8')
 out=execute_workflow(tmp_path,base,variant,[],include_method_example=True)
 assert abs(out['holdout_checks'][0]['pred_t80_min']-5.25871024926)<1e-8
 assert out['challenge']['error_min'] < -70
 assert out['steps'][0]['status']=='有缺口' and out['target_prediction_available'] is False
 assert out['changes'][0]['fields']['amount_mg']=={'before':20,'after':5}
 # Entire held-out formulation must stay out of both parameter fits.
 data['records']['CPV']['dt_s'][1]=1000
 data['records']['CPV']['t80_min'][1]=200
 p.write_text(json.dumps(data),encoding='utf-8')
 changed=execute_workflow(tmp_path,base,variant,[],include_method_example=True)
 assert changed['holdout_checks'][0]['pred_t80_min']==out['holdout_checks'][0]['pred_t80_min']
 assert changed['holdout_checks'][0]['error_min'] != out['holdout_checks'][0]['error_min']
 (tmp_path/path/'PMC8208916.xml').unlink()
 assert execute_workflow(tmp_path,base,variant,[],include_method_example=True)['holdout_checks']==[]

def test_actual_run_gets_execution_record_and_cannot_claim_completion(tmp_path):
 async def runner(s,rid,root):
  assert '本轮程序实际执行的四步验收' in s.run(rid)['message']
  s.finish(rid,'completed',report={'summary':'软件测试：假设模型声称完成','findings':[],'gaps':[]})
 app=create_app(tmp_path,runner=runner)
 with TestClient(app) as c:
  pid=c.post('/api/projects',json={'name':'workflow test','api':'A','market':'中国','strength':'5mg','strength_basis':'活性成分'}).json()['id']
  source=Store(tmp_path/'data/origin.sqlite3').add_evidence(pid,EvidenceInput(section='formulation',title='test',text='software fixture',basis='source',access='full_text',source_url='https://example.org/test',locator='fixture',applicability='test'))
  ingredients=[{'id':'a','role':'api','name':'A','amount_mg':5},{'id':'b','role':'excipient','name':'B','amount_mg':5}]
  base=c.post(f'/api/projects/{pid}/baselines',json={'title':'b','ingredients':ingredients,'process':'test','api_particle':'test','mass_basis':'test','source_ids':[source['id']],'rationale':'test'}).json()
  variant=c.post(f'/api/projects/{pid}/variants',json={'baseline_id':base['id'],'title':'v','ingredients':base['ingredients'],'method':'test'}).json()
  r=c.post(f'/api/projects/{pid}/excipient/runs',json={'variant_id':variant['id'],'question':'test'}).json()
  for _ in range(100):
   snap=c.get(f'/api/projects/{pid}').json()
   if snap['excipient']['runs'][-1]['status'] not in ('running','queued'):break
   time.sleep(.01)
  final=snap['excipient']['runs'][-1]
  assert final['status']=='partial'
  assert any('流程验收' in gap for gap in final['report']['gaps'])
  record=snap['research_workflows'][-1]
  assert record['run_id']==r['id'] and record['variant_id']==variant['id']
  assert record['holdout_checks']==[] and record['steps'][2]['status']=='缺来源数据'
  assert snap['baselines'][0]==base and snap['variants'][0]==variant
  assert c.post(f'/api/projects/{pid}/excipient/runs',json={'variant_id':'foreign','question':'test'}).status_code==404


def test_unrelated_case_not_automatically_selected(tmp_path):
 path=Path('reference/cross-formulation-validation-20260924')
 shutil.copytree(ROOT/path,tmp_path/path)
 base={'id':'b','ingredients':[{'id':'s','name':'特白玉米淀粉','amount_mg':8.5},{'id':'l','name':'乳糖','amount_mg':51.8}]}
 variant={'id':'v','ingredients':[{'id':'s','name':'特白玉米淀粉','amount_mg':17},{'id':'l','name':'乳糖','amount_mg':43.3}]}
 out=execute_workflow(tmp_path,base,variant,[])
 assert not out['holdout_checks'] and out['case_source'] is None
 assert 'MCC—PGS' not in str(out['steps'])
