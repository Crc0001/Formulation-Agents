import json
import pytest
from virtual_reactor_api.calculation_handoff import continuation_package
from virtual_reactor_api.calculation_handoff import saved_calculations

def test_current_and_explicit_checkpoint_records_preserve_diagnostics():
    ref='379c3299-85ff-416a-a202-efe736c7620a'
    model={'arms':[{'models':[{'parameters':{'tau_min':3},'residuals_pp':[1,-2],
            'internal_last_point_check':{'predicted':98,'observed':100}}]}]}
    def record(id,run):
        return dict(id=id,run_id=run,basis='hypothesis',title='source',
                    fields={'source_curve_model_json':json.dumps(model)})
    result=saved_calculations([record('new','current'),record(ref,'old'),record('other','unrelated')],
                              'current','screening',{'calculation_ids':[ref]})
    assert [r['id'] for r in result]==['new',ref]
    assert json.loads(result[1]['records']['source_curve_model_json'])==model

def test_no_unrelated_calculations_or_source_as_calculation():
    assert saved_calculations([dict(id='raw',run_id='current',fields={'text':'source'})],
                              'current','',None)==[]

def test_continuation_carries_previous_curve_and_reports_missing():
    variant={'id':'variant','baseline_id':'base'}
    curve_id='379c3299-85ff-416a-a202-efe736c7620a'
    previous={'id':'prior','project_id':'project','status':'partial','created_at':'2026-09-30',
              'message':'【处方辅料筛选】\n变化方案：'+json.dumps(variant)+'\n问题：研究',
              'report':{'screening_progress':{'calculation_evidence_ids':[curve_id,'missing']}}}
    evidence=[{'id':curve_id,'run_id':'earlier','basis':'hypothesis','title':'curve',
               'fields':{'source_curve_model_json':'{"arms":[{"models":[{"rmse_pp":2.38}]}]}'}}]
    package=continuation_package([previous],evidence,'project',variant)
    assert package['previous_run_id']=='prior'
    assert package['missing_calculation_ids']==['missing']
    sent=saved_calculations(evidence,'new',json.dumps(package),None)
    assert sent[0]['id']==curve_id
    assert 'rmse_pp' in sent[0]['records']['source_curve_model_json']
    for pid,v in [('other',variant),('project',{'id':'other','baseline_id':'base'}),
                  ('project',{'id':'variant','baseline_id':'other'})]:
        with pytest.raises(ValueError):continuation_package([previous],evidence,pid,v,'prior')
    with pytest.raises(ValueError):
        continuation_package([{**previous,'status':'running'}],evidence,'project',variant,'prior')
