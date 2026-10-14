import asyncio,json,copy
import pytest
from test_table_vision import Store,Model,reading
from virtual_reactor_api.table_vision import read_table,accepted_table
from virtual_reactor_api.origin_stages import origin_stage,stage_policy
from virtual_reactor_api.origin_completion import delivery_issues
from virtual_reactor_api.origin_delivery import CompactExtraction,expand_extraction,source_chunks
from virtual_reactor_api.capsule_models import ResearchReport
from virtual_reactor_api.capsule_research import validate_report


def test_wrong_table_rejected_and_cached(tmp_path):
    s=Store(tmp_path);r=reading();r['table_label']='Table 4'
    out=asyncio.run(read_table(s,'pid','r',tmp_path,'im','Table 3',Model([r])))
    assert out['status']=='unresolved' and not accepted_table(s.es[-1],s.es)
    assert asyncio.run(read_table(s,'pid','r',tmp_path,'im','Table 3',Model([])))['cached']


def test_provider_failure_archived_without_secret_and_cached(tmp_path):
    class Failed(Model):
        async def ainvoke(self,p):raise RuntimeError('secret-provider-body')
    s=Store(tmp_path)
    result=asyncio.run(read_table(s,'pid','r',tmp_path,'im','Table 3',Failed([])))
    assert result['status']=='unresolved'
    assert 'secret-provider-body' not in json.dumps(s.es)
    assert asyncio.run(read_table(s,'pid','r',tmp_path,'im','Table 3',Model([])))['cached']


def test_cancel_not_swallowed(tmp_path):
    class Cancel(Model):
        async def ainvoke(self,p):raise asyncio.CancelledError()
    s=Store(tmp_path)
    with pytest.raises(asyncio.CancelledError):asyncio.run(read_table(s,'pid','r',tmp_path,'im','Table 3',Cancel([])))


def test_merged_range_mismatch_rejected(tmp_path):
    s=Store(tmp_path);a=reading();a['cells'][1]['text']='';b=copy.deepcopy(a)
    a['cells'][0]['column_span']=2
    out=asyncio.run(read_table(s,'pid','r',tmp_path,'im','Table 3',Model([a,b,a])))
    assert out['status']=='unresolved'


def test_import_prefix_and_policy():
    assert origin_stage('【外部成果导入；原始运行 abc】【原研及处方工艺】【01阶段3】')==3
    assert origin_stage('历史文字【01阶段3】') is None
    assert 'read_source_table' in stage_policy(1)


def test_failed_delivery_blocked_but_scientific_unknown_allowed():
    report={'summary':'比较完成','gaps':['目标制造工艺未知'],'decision_comparison':{'rows':[{'metric':'来源','values':['未知']}]}}
    assert not delivery_issues(report,3)
    assert delivery_issues({**report,'gaps':['候选比较尚未完成（ValidationError）；已保留']},3)
    assert delivery_issues({**report,'decision_comparison':None},3)


def test_liquid_quantity_preserved_without_conversion():
    value=CompactExtraction.model_validate({'formulas':[{'title':'液剂','locator':'table','components':[{'name':'API','amount':5,'unit':'mg/mL','quantity_basis':'每mL溶液'},{'name':'水','amount':100,'unit':'mL'}]}]})
    result=expand_extraction(value,{'id':'s','basis':'source','text':''},{})
    a,b=result.formulations[0].components
    assert (a.source_amount,a.source_unit,a.source_quantity_basis)==(5,'mg/mL','每mL溶液')
    assert a.amount_mg is None and a.batch_amount is None and b.amount_mg is None


def test_comparison_unknown_reference_is_reported():
    r=ResearchReport(summary='done',findings=[],gaps=[],decision_comparison={'title':'comparison','candidates':['A'],'rows':[{'metric':'test','values':['v'],'source_ids':['wrong']}],'recommendation':'none','reasons':[],'limitations':[],'next_steps':[]})
    result,_=validate_report(r,[],organizer=True)
    assert any(g.startswith('比较表引用缺失：') for g in result.gaps)
    assert delivery_issues(result,3)


def test_origin_tool_registration():
    import ast
    from pathlib import Path
    tree=ast.parse(Path('apps/api/src/virtual_reactor_api/capsule_research.py').read_text('utf-8'))
    branches=[n.body for n in ast.walk(tree) if isinstance(n,ast.IfExp) and isinstance(n.test,ast.Name) and n.test.id=='is_origin' and isinstance(n.body,ast.List)]
    assert any('read_source_table' in [x.id for x in b.elts if isinstance(x,ast.Name)] for b in branches)


def test_visual_table_can_enter_origin_extraction_without_promotion(tmp_path):
    s=Store(tmp_path)
    for e in s.es:e.update(text='source',title='source',source_url='https://example.org',locator='page')
    result=asyncio.run(read_table(s,'pid','r',tmp_path,'im','Table 3',Model([reading(),reading()])))
    chunks=source_chunks(s.es)
    assert any(c['id']==result['evidence_id'] and c['basis']=='image_estimate' for c in chunks)


def test_fixed_comparison_reference_clears_derived_blocker():
    r=ResearchReport(summary='done',findings=[],gaps=['比较表引用缺失：test：wrong'],decision_comparison={'title':'comparison','candidates':['A'],'rows':[{'metric':'test','values':['v'],'source_ids':['right']}],'recommendation':'none','reasons':[],'limitations':[],'next_steps':[]})
    result,_=validate_report(r,[{'id':'right','access':'full_text','basis':'source','text':'v','title':'source','source_url':'https://example.org'}],organizer=True)
    assert not any(g.startswith('比较表引用缺失：') for g in result.gaps)
