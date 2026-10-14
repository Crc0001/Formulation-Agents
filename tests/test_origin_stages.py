import asyncio
from virtual_reactor_api.origin_stages import origin_stage,origin_message,scope_report,recover_stage_one,IDENTITY_ROWS,IdentitySummary
from virtual_reactor_api.capsule_models import ResearchReport
from virtual_reactor_api.capsule_research import validate_report

def test_request_scoped_before_history():
    q='第一阶段：原研确认与说明书组成。'
    m=origin_message(q)
    assert origin_stage(m)==1
    assert 'model-led-v1' not in m and '每个模型必须' not in m
    assert origin_stage('【原研及处方工艺】【接续：汇总】【01阶段1】仅整理')==1
    assert origin_stage('【原研及处方工艺】第二阶段：追溯；历史提及第一阶段')==2
    assert origin_stage('第三阶段：比较')==3
    assert origin_stage('请比较；历史第一阶段：') is None

def identity():
    return ResearchReport(summary='身份稿',findings=[],gaps=[],decision_comparison=dict(title='身份',candidates=['A'],recommendation='身份仍待核',rows=[dict(metric=k,values=['未核实'],source_ids=[]) for k in IDENTITY_ROWS],reasons=[],limitations=[],next_steps=[]))

def test_stage_one_does_not_demand_design_patent_or_recommendation():
    r=identity()
    result,issues=validate_report(r,[],origin_phase=1)
    assert not issues and result.origin_recommendation is None
    r.decision_comparison.rows.pop()
    _,issues=validate_report(r,[],origin_phase=1)
    assert issues==['第一阶段未交付：说明书辅料组成']

def test_scope_does_not_change_original_or_drop_quantities():
    r=identity()
    r.origin_recommendation=dict(formula_title='old',rationale='old',process='old')
    scoped=scope_report(r,1)
    assert scoped.origin_recommendation is None
    assert r.origin_recommendation is not None
    assert scoped.decision_comparison==r.decision_comparison

class Model:
    def with_structured_output(self,schema,**kw):
        assert schema is IdentitySummary
        return self
    async def ainvoke(self,messages):
        assert '当前为无工具归档整理' in messages[0]['content']
        r=identity()
        return IdentitySummary(summary=r.summary,gaps=r.gaps,decision_comparison=r.decision_comparison)

def test_identity_recovery_has_no_formula_prerequisite():
    saved=[]
    result=asyncio.run(recover_stage_one(Model(),[],{},None,saved.append,lambda *args:None,lambda r,e:validate_report(r,e,origin_phase=1)))
    assert saved and not result.formulations and result.decision_comparison
    assert result.origin_recommendation is None

def test_http_start_does_not_append_old_model_contract(tmp_path):
    from fastapi.testclient import TestClient
    from virtual_reactor_api.dual_main import create_app
    (tmp_path/'reference').mkdir()
    (tmp_path/'reference/model-led-contract.md').write_text('OLD MODEL CONTRACT MUST NOT LEAK',encoding='utf-8')
    with TestClient(create_app(tmp_path,runner=lambda *args:None)) as c:
        p=c.post('/api/projects',json={'name':'stage test','api':'test','market':'中国','strength':'500mg','strength_basis':'活性成分'}).json()
        r=c.post('/api/projects/'+p['id']+'/origin/runs',json={'question':'第一阶段：核对身份'})
        assert r.status_code==200,r.text
        message=r.json()['message']
        assert origin_stage(message)==1
        assert 'OLD MODEL CONTRACT' not in message
        assert '已有独立保存的三阶段数值复算' not in message
        assert '输出推荐基准origin_recommendation' not in message

def test_interruption_dict_remains_serializable_and_preserves_checkpoint():
    from virtual_reactor_api.research_limits import interruption_report
    import json
    checkpoint=identity().model_dump()
    result=scope_report(interruption_report([], 'r', '步骤上限', checkpoint),1)
    assert isinstance(result,dict)
    assert result['decision_comparison']==checkpoint['decision_comparison']
    assert '步骤上限' in json.dumps(result,ensure_ascii=False)
    assert checkpoint['summary']=='身份稿'

def test_identity_packet_prioritizes_original_and_keeps_provenance():
    from virtual_reactor_api.origin_stages import identity_sources
    sources=[dict(id='old',title='patent',text='unrelated',fields={}),dict(id='new',title='目录',text='full',basis='source',access='full_text',source_url='https://example.org',fields={'identity_priority':'true','identity_excerpt':'11-4 原表行'})]
    result=identity_sources(sources)
    assert len(result)==1 and result[0]['id']=='new'
    assert result[0]['text']=='11-4 原表行' and result[0]['excerpt_only']
    assert sources[1]['text']=='full'

def test_stage_one_background_completion_has_no_later_stage_gates(tmp_path):
    from fastapi.testclient import TestClient
    from virtual_reactor_api.dual_main import create_app
    import time
    async def runner(store,run_id,root):
        store.finish(run_id,'completed',report=identity().model_dump())
    with TestClient(create_app(tmp_path,runner=runner)) as c:
        p=c.post('/api/projects',json={'name':'stage finish','api':'test','market':'中国','strength':'500mg','strength_basis':'活性成分'}).json()
        r=c.post('/api/projects/'+p['id']+'/origin/runs',json={'question':'第一阶段：核对身份'}).json()
        for _ in range(30):
            snap=c.get('/api/projects/'+p['id']).json()
            saved=next(x for x in snap['origin']['runs'] if x['id']==r['id'])
            if saved['status']!='running':break
            time.sleep(.02)
        assert saved['status']=='completed',saved
        assert saved['report']['gaps']==[]
        assert 'model_design_audit' not in saved

def test_only_resolved_generated_gaps_removed_without_mutating_history():
    r=identity()
    r.gaps=['第一阶段未交付：'+name for name in IDENTITY_ROWS]+['监管原文尚未取得']
    r.decision_comparison.rows.pop()
    scoped=scope_report(r,1)
    assert scoped.gaps==['第一阶段未交付：说明书辅料组成','监管原文尚未取得']
    assert len(r.gaps)==7
    assert scope_report(r.model_dump(),1)['gaps']==scoped.gaps
