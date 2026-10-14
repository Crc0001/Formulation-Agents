import pytest
from virtual_reactor_api.agent_split import inventory,design,DoeInput,audit_organization,ORGANIZE_MARKER
from virtual_reactor_api.dual_main import create_app
from fastapi.testclient import TestClient
from virtual_reactor_api.capsule_models import EvidenceInput
from virtual_reactor_api.capsule_store import Store

def base():return {'id':'b','ingredients':[{'id':'api','name':'API','role':'api','amount_mg':.5},{'id':'l','name':'乳糖','role':'excipient','amount_mg':51.8},{'id':'m','name':'微晶纤维素','role':'excipient','amount_mg':29},{'id':'s','name':'淀粉','role':'excipient','amount_mg':8.5},{'id':'c','name':'硬脂酸钙','role':'excipient','amount_mg':.2}]}

def test_inventory_covers_all_pairs_without_api():
 i=inventory(base());assert len(i['materials'])==4 and len(i['pairs'])==6
 assert all('api' not in [p['left_id'],p['right_id']] for p in i['pairs'])

def test_doe_preserves_mass_and_fixed_ingredients():
 d=design(base(),DoeInput(baseline_id='b',filler_id='l',factors=[dict(ingredient_id='s',low_mg=6,high_mg=10),dict(ingredient_id='m',low_mg=25,high_mg=30)],rationale='测试范围'))
 assert len(d['points'])==9
 for p in d['points']:
  assert abs(sum(p['amounts_mg'].values())-90)<1e-9
  assert p['amounts_mg']['api']==.5 and p['amounts_mg']['c']==.2

@pytest.mark.parametrize('fid,lo,hi,fill',[('api',1,2,'l'),('s',1,2,'s'),('s',10,9,'l'),('s',80,90,'l')])
def test_bad_doe_rejected(fid,lo,hi,fill):
 with pytest.raises(ValueError):design(base(),DoeInput(baseline_id='b',filler_id=fill,factors=[dict(ingredient_id=fid,low_mg=lo,high_mg=hi)],rationale='非法测试'))

def test_missing_package_not_complete():
 assert audit_organization(None,base(),[])
 assert audit_organization({'materials':[],'pairs':[]},base(),[])

def test_02_runs_without_variant_and_hands_packet_to_03(tmp_path):
 seen=[]
 async def runner(store,rid,root):
  r=store.run(rid);seen.append(r['message'])
  store.finish(rid,'partial',report={'summary':'测试研究包','findings':[],'gaps':['仅软件测试'],'excipient_organization':{'materials':[],'pairs':[],'next_research':['补查']}})
 with TestClient(create_app(tmp_path,runner=runner)) as c:
  p=c.post('/api/projects',json={'name':'三智能体测试','api':'API','market':'中国','strength':'0.5mg','strength_basis':'活性'}).json();pid=p['id']
  e=Store(tmp_path/'data/origin.sqlite3').add_evidence(pid,EvidenceInput(section='formulation',title='测试来源',text='TEST',basis='source',access='full_text',source_url='https://example.org',locator='test',applicability='test'))
  b=c.post(f'/api/projects/{pid}/baselines',json={'title':'测试基准','ingredients':base()['ingredients'],'process':'固定工艺','api_particle':'未知','mass_basis':'mg','source_ids':[e['id']],'rationale':'test'}).json()
  assert c.post(f'/api/projects/{pid}/organize/runs',json={'question':'整理'}).status_code==422
  r=c.post(f'/api/projects/{pid}/organize/runs',json={'question':'全方整理','baseline_id':b['id']})
  assert r.status_code==200 and ORGANIZE_MARKER in r.json()['message']
  snap=c.get('/api/projects/'+pid).json()
  assert len(snap['organize']['runs'])==1 and not snap['excipient']['runs']
  assert len(snap['organization_runs'][0]['inventory']['pairs'])==6
  assert c.get(f'/api/projects/{pid}/inventory/{b["id"]}').status_code==200
  v=c.post(f'/api/projects/{pid}/variants',json={'baseline_id':b['id'],'title':'test','ingredients':b['ingredients'],'method':'同方法'}).json()
  r3=c.post(f'/api/projects/{pid}/excipient/runs',json={'question':'模拟','variant_id':v['id']})
  assert r3.status_code==200 and '02已交付研究包' in r3.json()['message']
  assert len(c.get('/api/projects/'+pid).json()['baselines'])==1


def test_review_keeps_original_report_and_distinguishes_requests():
 from copy import deepcopy
 from virtual_reactor_api.agent_split import organization_review
 r={'report':{'gaps':['未交付替换对照分析'],'excipient_organization':{'materials':[],'pairs':[]}}}
 before=deepcopy(r)
 review=organization_review(r,base(),[],[{'kind':'search_request'},{'kind':'search_error'},{'kind':'document_request'}])
 assert r==before
 assert review['obsolete_checks']==['未交付替换对照分析']
 assert review['activity']['search_requests']==1 and review['activity']['search_errors']==1
 assert review['issues'] and review['materials']==0

def test_workbook_alias_requires_registered_verified_source():
 r={'materials':[dict(ingredient_id='l',functional_features='候选',brand_grade_options='待核',research_notes='原粉',source_ids=['hash'])],'pairs':[]}
 assert any('hash' in x for x in audit_organization(r,base(),[]))
 e={'id':'real','access':'imported','fields':{'verified_workbook_sha256':'hash'}}
 assert not any('hash' in x for x in audit_organization(r,base(),[e]))
 assert any('目录' in x for x in audit_organization(r,base(),[e]))


def test_citation_correction_requires_matching_original_quote():
 from virtual_reactor_api.agent_split import citation_corrections
 target={'id':'real','title':'原文','access':'page_text','basis':'source','text':'abcdefghijklmno'}
 fix={'id':'fix','fields':{'citation_alias_from':'typo','citation_alias_to':'real','citation_source_quote':'abcdefghijklmno'}}
 assert citation_corrections([target,fix])[0]['to']=='real'
 fix['fields']['citation_source_quote']='wrong quoted passage'
 assert citation_corrections([target,fix])==[]


def test_validation_requires_frozen_hypothesis(tmp_path):
 async def runner(store,rid,root):store.finish(rid,'partial',report={'summary':'假设稿','findings':[],'gaps':[]})
 with TestClient(create_app(tmp_path,runner=runner)) as c:
  pid=c.post('/api/projects',json={'name':'hypothesis','api':'API','market':'中国','strength':'0.5mg','strength_basis':'活性'}).json()['id']
  st=Store(tmp_path/'data/origin.sqlite3');e=st.add_evidence(pid,EvidenceInput(section='formulation',title='source',text='text',basis='source',source_url='https://example.org',locator='p1',applicability='test'))
  b=c.post(f'/api/projects/{pid}/baselines',json={'title':'b','ingredients':base()['ingredients'],'process':'fixed','api_particle':'unknown','mass_basis':'mg','source_ids':[e['id']],'rationale':'test'}).json()
  v=c.post(f'/api/projects/{pid}/variants',json={'baseline_id':b['id'],'title':'v','ingredients':b['ingredients'],'method':'water'}).json()
  assert c.post(f'/api/projects/{pid}/excipient/runs',json={'question':'verify','variant_id':v['id'],'research_phase':'validation'}).status_code==422
  r=c.post(f'/api/projects/{pid}/excipient/runs',json={'question':'hypothesis','variant_id':v['id']}).json()
  assert '【假设建立阶段】' in r['message']
  assert not c.get('/api/projects/'+pid).json()['research_workflows']
  assert c.post(f'/api/projects/{pid}/hypotheses',json={'run_id':r['id'],'variant_id':v['id'],'prediction':'expected result with conditions','falsifier':'different observed result'}).status_code==422

@pytest.mark.parametrize('enabled,count,pairs',[(False,4,6),(True,5,10)])
def test_coating_scope_frozen_in_run_and_review(tmp_path,enabled,count,pairs):
 import copy
 from virtual_reactor_api.agent_split import organization_scope
 original=base();original['ingredients'].append({'id':'coat','name':'薄膜包衣','role':'shell','amount_mg':3})
 before=copy.deepcopy(original)
 inv=inventory(original,enabled)
 assert len(inv['materials'])==count and len(inv['pairs'])==pairs
 assert original==before
 packet={'materials':[dict(ingredient_id=m['id'],functional_features='待核',brand_grade_options='待核',research_notes='待核',gaps=['缺原文']) for m in inv['materials']], 'pairs':[dict(left_id=p['left_id'],right_id=p['right_id'],relationship='待核',research_notes='待核',gaps=['缺原文']) for p in inv['pairs']]}
 assert not audit_organization(packet,original,[],enabled)
 assert audit_organization(packet,original,[],not enabled)
 async def runner(store,rid,root):
  store.finish(rid,'partial',report={'summary':'scope test','findings':[],'gaps':[],'excipient_organization':packet})
 with TestClient(create_app(tmp_path,runner=runner)) as c:
  pid=c.post('/api/projects',json={'name':'scope','api':'API','market':'中国','strength':'0.5mg','strength_basis':'活性'}).json()['id']
  e=Store(tmp_path/'data/origin.sqlite3').add_evidence(pid,EvidenceInput(section='formulation',title='test',text='test source',basis='source',access='full_text',source_url='https://example.org',locator='test',applicability='test'))
  b=c.post(f'/api/projects/{pid}/baselines',json={'title':'test','ingredients':original['ingredients'],'process':'固定工艺','api_particle':'未知','mass_basis':'mg','source_ids':[e['id']],'rationale':'test'}).json()
  args={'question':'全部辅料','baseline_id':b['id']}
  if enabled:args['include_coating']=True
  r=c.post(f'/api/projects/{pid}/organize/runs',json=args)
  assert r.status_code==200
  assert organization_scope(enabled) in r.json()['message']
  snap=c.get('/api/projects/'+pid).json()
  binding=snap['organization_runs'][0]
  assert binding['include_coating']==enabled and len(binding['inventory']['pairs'])==pairs
  review=snap['organize']['runs'][0]['organization_review']
  assert review['expected_materials']==count and review['expected_pairs']==pairs and not review['issues']
  preview=c.get(f'/api/projects/{pid}/inventory/{b["id"]}?include_coating={str(enabled).lower()}').json()
  assert len(preview['pairs'])==pairs
  assert c.get('/api/projects/'+pid).json()['baselines'][0]['ingredients']==b['ingredients']

