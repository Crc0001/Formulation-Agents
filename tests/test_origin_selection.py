from virtual_reactor_api.capsule_models import ResearchReport
from virtual_reactor_api.origin_selection import audit_selection, REQUIRED_ROWS

def report(rows):
    return ResearchReport.model_validate(dict(summary='candidate',findings=[],gaps=[],origin_recommendation=dict(formula_title='A',rationale='test',process='unknown'),decision_comparison=dict(title='test',recommendation='test',candidates=['A'],rows=rows,reasons=[],limitations=[],next_steps=[])))

def test_missing_match_evidence_does_not_pass_silently_or_invent_rows():
    original=report([])
    checked=audit_selection(original)
    assert checked.gaps and '未完整' in checked.gaps[0]
    assert checked.decision_comparison.rows==[]
    assert not original.gaps
    assert len(audit_selection(checked).gaps)==1

def test_explicit_unknown_rows_remain_unknown_not_upgraded_to_match():
    original=report([dict(metric=k,values=['未核实'],source_ids=[]) for k in REQUIRED_ROWS])
    result=audit_selection(original)
    assert result==original
    assert all(r.values==['未核实'] for r in result.decision_comparison.rows)

def test_repaired_comparison_removes_only_obsolete_mechanical_warning():
    checked=audit_selection(report([]))
    checked.gaps.append('商业关联待核')
    checked.decision_comparison=report([dict(metric=k,values=['未核实'],source_ids=[]) for k in REQUIRED_ROWS]).decision_comparison
    repaired=audit_selection(checked)
    assert repaired.gaps==['商业关联待核']
    assert not repaired.origin_recommendation.limitations

def test_qualitative_label_cannot_silently_be_experimental_recommendation():
    original=report([dict(metric=k,values=['未核实'],source_ids=[]) for k in REQUIRED_ROWS])
    from virtual_reactor_api.capsule_models import RetrievedFormula
    original.formulations=[RetrievedFormula.model_validate(dict(title='A',product='label',dosage_form='tablet',source_role='official_label',source_ids=[],locator='label',components=[dict(name='乳糖',compartment='fill')],applicability='identity only'))]
    checked=audit_selection(original)
    assert any('第一阶段' in g for g in checked.gaps)
    assert checked.formulations==original.formulations
    assert not original.gaps
    assert audit_selection(checked)==checked
    original.formulations[0].components[0].percent=56
    assert not audit_selection(original).gaps
