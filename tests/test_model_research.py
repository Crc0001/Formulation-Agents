import pytest
from pydantic import ValidationError
from virtual_reactor_api.model_research import ResearchDesign,audit_design
from virtual_reactor_api.capsule_models import ResearchReport

def design():
 return {'question':'test','scope':'software only','hypotheses':[{'id':m,'title':m,'kind':'mechanistic','equation':'y=k*x','mapping':'x to y','parameters':'test only','domain':'test','source_ids':['s'],'calibration':'separate','holdout':'separate','falsifier':'observed difference'} for m in ['a','b']], 'anchors':[{'id':'x','condition':'same conditions','observable':'Q15','unit':'pp','purpose':'discrimination','predictions':[{'model_id':'a','value':10,'calculation_evidence_id':'c'},{'model_id':'b','value':16,'calculation_evidence_id':'c'}],'measurement_sd':2,'sd_source_id':'s','qualitative_predictions':'different','decision_rule':'test only','priority_reason':'difference'}]}

def test_legacy_report_remains_readable():
 assert ResearchReport(summary='old',findings=[],gaps=[]).research_design is None

def test_separation_is_calculated_and_evidence_gated():
 evidence=[{'id':'s','basis':'source','access':'full_text'},{'id':'c','basis':'hypothesis','access':'imported'}]
 out=audit_design(design(),evidence)
 assert out['anchors'][0]['spread']==6 and out['anchors'][0]['normalized_separation']==3
 assert audit_design(design(),evidence[:1])['anchors'][0]['spread'] is None
 assert audit_design(design(),evidence[1:])['anchors'][0]['normalized_separation'] is None

def test_unknown_or_duplicate_models_rejected():
 d=design();d['anchors'][0]['predictions'][1]['model_id']='unknown'
 with pytest.raises(ValidationError):ResearchDesign.model_validate(d)
 d=design();d['hypotheses'][1]['id']='a'
 with pytest.raises(ValidationError):ResearchDesign.model_validate(d)

def test_qualitative_anchor_not_assigned_numeric_score():
 d=design();d['anchors'][0]['predictions']=[]
 assert audit_design(d,[])['anchors'][0]['spread'] is None

def test_nonfinite_and_zero_noise_rejected():
 for value in [0,float('nan'),float('inf')]:
  d=design();d['anchors'][0]['measurement_sd']=value
  with pytest.raises(ValidationError):ResearchDesign.model_validate(d)

def test_api_keeps_design_and_read_only_audit(tmp_path):
 from fastapi.testclient import TestClient
 from virtual_reactor_api.dual_main import create_app
 from virtual_reactor_api.capsule_store import Store
 from virtual_reactor_api.capsule_models import ProjectInput
 store=Store(tmp_path/'data/origin.sqlite3')
 app=create_app(tmp_path,runner=lambda *args:None)
 with TestClient(app) as client:
  p=client.post('/api/projects',json={'name':'模型包测试','api':'test','market':'test','strength':'1mg','strength_basis':'test'}).json()
  r=store.create_run(p['id'],'test')
  report=ResearchReport(summary='test only',findings=[],gaps=[],research_design=ResearchDesign.model_validate(design())).model_dump()
  store.finish(r['id'],'partial',report=report)
  response=client.get('/api/projects/'+p['id'])
  assert response.status_code==200
  result=next(x for x in response.json()['origin']['runs'] if x['id']==r['id'])
  assert result['report']['research_design']['question']=='test'
  assert result['model_design_audit']['anchors'][0]['spread'] is None
  assert 'model_design_audit' not in store.run(r['id'])
  assert store.run(r['id'])['report']==report
