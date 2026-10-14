import json
from fastapi.testclient import TestClient
from virtual_reactor_api.dual_main import create_app
from virtual_reactor_api.capsule_store import Store
from virtual_reactor_api.capsule_models import EvidenceInput,ProjectInput
from virtual_reactor_api.interaction_agent import share_sources,audit_interactions,INTERACTION_MARKER
from virtual_reactor_api.origin_delivery import merge_report
from test_agent_split import base

def study():
 return dict(left_id='l',right_id='s',evidence_scope='not_found',conditions='test',response='Q %',observed_relation='未知',mechanism_hypothesis='待检验',equation='待估计',parameter_basis='无数据',applicability='未验证',gaps=['缺数据'])

def test_checkpoints_accumulate_and_empty_final_preserves():
 a=dict(summary='first',findings=[],gaps=[],interaction_research={'studies':[study()],'next_research':['查原文']})
 b=dict(summary='end',findings=[],gaps=[])
 merged=merge_report(a,b)
 assert len(merged.interaction_research.studies)==1
 assert len(merge_report(merged,a).interaction_research.studies)==1
 bad=study();bad['right_id']='api'
 assert '配对不属于冻结基准辅料' in audit_interactions({'studies':[bad]},base(),[])

def test_source_sharing_is_idempotent_and_does_not_promote_hypothesis(tmp_path):
 a,b=Store(tmp_path/'a.db'),Store(tmp_path/'b.db')
 for store in (a,b):
  for pid in ('p','other'):store.create_project(ProjectInput(name='test',api='API',market='China',strength='0.5mg',strength_basis='active'),pid)
 for basis in ('source','hypothesis','search_lead'):
  a.add_evidence('p',EvidenceInput(section='comparison',title=basis,text='original',basis=basis,access='page_text',applicability='software test',source_url='https://example.org/test',locator='table 1'))
 a.add_evidence('other',EvidenceInput(section='comparison',title='other',text='private',basis='source',access='page_text',applicability='software test',source_url='https://example.org/test',locator='table 1'))
 assert share_sources(a,b,'p')==1
 assert share_sources(a,b,'p')==0
 assert len(b.rows('evidence','p'))==1 and not b.rows('evidence','other')
 assert b.rows('evidence','p')[0]['basis']=='source'

def test_independent_runs_archive_and_same_baseline_handoff(tmp_path):
 async def runner(store,rid,root):
  pid=store.run(rid)['project_id']
  if INTERACTION_MARKER in store.run(rid)['message']:
   store.add_evidence(pid,EvidenceInput(section='comparison',title='new original',text='source',basis='source',access='page_text',applicability='software test',source_url='https://example.org/test',locator='table 1'),rid)
   store.finish(rid,'partial',report=dict(summary='pair archive',findings=[],gaps=[],interaction_research={'studies':[study()],'next_research':['continue']}))
  else:store.finish(rid,'partial',report=dict(summary='test',findings=[],gaps=[]))
 with TestClient(create_app(tmp_path,runner)) as c:
  pid=c.post('/api/projects',json=dict(name='test',api='API',market='China',strength='0.5mg',strength_basis='active')).json()['id']
  origin=Store(tmp_path/'data/origin.sqlite3')
  e=origin.add_evidence(pid,EvidenceInput(section='formulation',title='source',text='source',basis='source',access='page_text',applicability='software test',source_url='https://example.org/test',locator='table 1'))
  body=dict(title='base',ingredients=base()['ingredients'],process='fixed',api_particle='unknown',mass_basis='mg',source_ids=[e['id']],rationale='test')
  b=c.post(f'/api/projects/{pid}/baselines',json=body).json()
  assert c.post(f'/api/projects/{pid}/interaction/runs',json={'question':'test'}).status_code==422
  for _ in range(2):
   result=c.post(f'/api/projects/{pid}/interaction/runs',json={'question':'test','baseline_id':b['id'],'research_target':{'kind':'pair','material_ids':['l','s'],'objective':'乳糖淀粉配比与溶出'}})
   assert result.status_code==200
  snap=c.get('/api/projects/'+pid).json()
  assert len(snap['interaction']['runs'])==2 and len(snap['interaction_runs'])==2
  assert len(snap['baselines'])==1 and not snap['variants']
  assert any(e['title']=='new original' for e in snap['organize']['evidence'])
  def start_doe(baseline):
   v=c.post(f'/api/projects/{pid}/variants',json=dict(baseline_id=baseline['id'],title='v',ingredients=baseline['ingredients'],method='water')).json()
   return c.post(f'/api/projects/{pid}/excipient/runs',json=dict(question='simulate',variant_id=v['id'])).json()['message']
  assert '03配对研究版本' in start_doe(b)
  other=c.post(f'/api/projects/{pid}/baselines',json={**body,'title':'other'}).json()
  assert '03配对研究版本' not in start_doe(other)
 # Existing project gets its new independent store on upgrade, without new project IDs.
 with TestClient(create_app(tmp_path,runner)) as c:
  assert len(c.get('/api/projects/'+pid).json()['interaction_runs'])==2




def test_target_scope_and_grade_comparisons():
 from virtual_reactor_api.interaction_agent import ResearchTarget,validate_target
 import pytest
 target=validate_target(ResearchTarget(kind='grade',material_ids=['l'],objective='乳糖不同粒径的影响'),base())
 for kind,ids in [('grade',['l','s']),('pair',['l']),('pair',['api','s']),('pair',['l','l'])]:
  with pytest.raises(ValueError):validate_target(ResearchTarget(kind=kind,material_ids=ids,objective='test'),base())
 item={**study(),'study_kind':'grade','left_id':'l','right_id':'l','left_condition':'粒径30微米','right_condition':'粒径100微米'}
 issues=audit_interactions({'studies':[item]},base(),[],target)
 assert not any('基准辅料' in i or '偏离' in i or '两臂' in i for i in issues)
 item['right_condition']=''
 assert any('两臂' in i for i in audit_interactions({'studies':[item]},base(),[],target))
 assert any('偏离' in i for i in audit_interactions({'studies':[study()]},base(),[],target))


def test_no_depth_contract_does_not_crash_02_or_03():
 from virtual_reactor_api.capsule_research_plan import research_gaps
 assert research_gaps(None,[],None)==[]
 assert research_gaps([],[],None)==[]
 assert research_gaps(('专项',{'paper'},False),[],None)


def test_deepening_carries_prior_gaps_and_counts_only_new_files():
 from virtual_reactor_api.interaction_agent import continuation_context,research_increment
 r={'id':'previous','report':{'interaction_research':{'studies':[study()],'next_research':['query']}}}
 context=continuation_context(r)
 assert context['unresolved_gaps']==['缺数据'] and context['next_research']==['query']
 old={'id':'old','basis':'source','access':'full_text','fields':{'sha256':'same'}}
 repeated={**old,'id':'repeat','run_id':'current'}
 new={**repeated,'id':'new','fields':{'sha256':'new'}}
 calc={'id':'calc','run_id':'current','basis':'hypothesis','fields':{'source_curve_model_json':'{}'}}
 result=research_increment([old],[old,repeated,new,calc],'current')
 assert result['new_source_files']==1 and result['calculation_ids']==['calc']

def test_source_case_preserved_and_validation_audited():
 case=dict(name='可计算来源',drug='其它药',selection_reason='原表完整',response='崩解 min',data_completeness='三水平',source_ids=['s1'],calculation_ids=['c1'],validation_kind='internal_holdout',validation_result='内部留出',target_transfer='尚未迁移')
 a=dict(summary='source',findings=[],gaps=[],interaction_research={'studies':[study()],'source_case':case})
 merged=merge_report(a,dict(summary='end',findings=[],gaps=[]))
 assert merged.interaction_research.source_case.drug=='其它药'
 evidence=[dict(id='s1',basis='source',access='page_text'),dict(id='c1',basis='hypothesis',fields={'source_response_model_json':'{}'})]
 issues=audit_interactions(merged.interaction_research.model_dump(),base(),evidence)
 assert not any('来源案例' in x for x in issues)
 merged.interaction_research.source_case.calculation_ids=['missing']
 assert any('来源案例未绑定计算记录' in x for x in audit_interactions(merged.interaction_research.model_dump(),base(),evidence))
 merged.interaction_research.source_case.validation_kind='independent'
 assert any('独立验证声明待核对' in x for x in audit_interactions(merged.interaction_research.model_dump(),base(),evidence))

def test_pair_lanes_require_balance_and_real_pair_calculation():
 p=study();p.update(evidence_lane='direct_exchange',effect_identity='exchange_effect')
 target={'kind':'pair','material_ids':['l','s']}
 issues=audit_interactions({'studies':[p]},base(),[],target)
 assert any('缺补差' in x for x in issues)
 synth=dict(left_material_id='l',right_material_id='s',left_evidence_status='missing',right_evidence_status='source',direct_exchange_status='missing',comparability='unknown',main_hypothesis='additive',competing_hypothesis='nonlinear',difference_equation='delta',coefficient_basis='unknown',next_action='find lactose',status='source_calculated',calculation_ids=['single'])
 packet={'studies':[p],'pair_synthesis':synth}
 issues=audit_interactions(packet,base(),[{'id':'single','fields':{'source_response_model_json':'{}'}}],target)
 assert any('不等于配对' in x for x in issues)
 a=dict(summary='a',findings=[],gaps=[],interaction_research=packet)
 merged=merge_report(a,dict(summary='later',findings=[],gaps=[]))
 assert merged.interaction_research.pair_synthesis.next_action=='find lactose'
