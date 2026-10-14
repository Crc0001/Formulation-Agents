import asyncio,json
import pytest
from test_origin_batch import setup
from virtual_reactor_api.research_limits import model_wait_seconds
from virtual_reactor_api.origin_stages import IdentitySummary, recover_stage_one, IDENTITY_ROWS
from virtual_reactor_api.capsule_models import ResearchReport

def test_wait_policy_and_small_schema():
    assert model_wait_seconds('openai:glm-5.2')==300
    assert model_wait_seconds('openai:glm-5.2',recovery=True)==300
    assert model_wait_seconds('openai:gpt-6-astra')==600
    assert model_wait_seconds('anthropic:other')==120
    assert len(json.dumps(IdentitySummary.model_json_schema()))<len(json.dumps(ResearchReport.model_json_schema()))/4

def blocked(tmp_path):
    q,calls=setup(tmp_path);s=q.load(108);i=s['items'][0]
    r=q.store.create_run(i['project_id'],'【01阶段1】【108批整批建档:108-1:阶段1】')
    q.store.finish(r['id'],'partial',error='timeout')
    i.update(status='中断待核',phases=[{'phase':1,'run_id':r['id'],'status':'partial','delivery_issues':['missing']}]);q.save(s)
    return q,calls,r,i['project_id']

def test_retry_preserves_history_and_does_not_reuse_failed_run(tmp_path):
    q,calls,r,pid=blocked(tmp_path)
    asyncio.run(q.retry(108,pid,'glm',True))
    s=q.load(108);assert s['items'][0]['attempt_history'][0]['run_id']==r['id']
    assert q.store.run(r['id'])['error']=='timeout'
    asyncio.run(q.tick());s=q.load(108)
    assert len(calls)==1 and calls[0].startswith('【接续：汇总】【01阶段1】')
    assert s['items'][0]['phases'][0]['phase']==1
    assert s['items'][0]['phases'][0]['run_id']!=r['id']
    assert 'retry_request' not in s['items'][0]

def test_retry_duplicate_and_unknown_rejected(tmp_path):
    q,calls,r,pid=blocked(tmp_path)
    with pytest.raises(ValueError):asyncio.run(q.retry(108,'wrong','glm'))
    asyncio.run(q.retry(108,pid,'glm'))
    with pytest.raises(ValueError):asyncio.run(q.retry(108,pid,'glm'))

def test_identity_summary_still_validates_and_keeps_sources():
    saved=[];seen=[]
    report=IdentitySummary(summary='identity',gaps=['unknown'],decision_comparison={'title':'identity','recommendation':'review','candidates':['A'],'rows':[{'metric':x,'values':['unknown'],'source_ids':['e1']} for x in IDENTITY_ROWS],'reasons':[],'limitations':[],'next_steps':[]})
    class Writer:
        async def ainvoke(self,messages):return report
    class Model:
        def with_structured_output(self,schema,method,include_raw):
            assert schema is IdentitySummary
            return Writer()
    def validate(r,e):seen.append(r);return r,[]
    result=asyncio.run(recover_stage_one(Model(),[],{'api':'test'},None,saved.append,lambda *args:None,validate))
    assert isinstance(result,ResearchReport) and len(saved)==1 and seen
    assert result.decision_comparison.rows[0].source_ids==['e1']


def test_identity_invalid_output_repairs_once_and_records_safe_metadata():
    from pydantic import ValidationError
    from types import SimpleNamespace
    try:IdentitySummary.model_validate({})
    except ValidationError as e:error=e
    raw=SimpleNamespace(response_metadata={'finish_reason':'length'},usage_metadata={'output_tokens':6000})
    events=[];calls=[]
    class Writer:
        async def ainvoke(self,messages):
            calls.append(len(messages))
            return {'raw':raw,'parsed':None,'parsing_error':error}
    class Model:
        def with_structured_output(self,*args,**kwargs):return Writer()
    with pytest.raises(ValidationError):
        asyncio.run(recover_stage_one(Model(),[],{},None,lambda r:None,lambda k,p:events.append((k,p)),lambda r,e:(r,[])))
    assert calls==[2,3] and len(events)==2
    assert events[0][1]['finish_reason']=='length'
    assert all('input' not in field for field in events[0][1]['fields'])


def test_source_prefix_normalization_unique_only_preserves_history():
    from virtual_reactor_api.capsule_research import normalize_source_ids
    from virtual_reactor_api.capsule_models import ResearchReport
    a='ed9c7a9a-1111-2222-3333-444444444444';b='050e188e-1111-2222-3333-444444444444'
    r=ResearchReport(summary='test',findings=[],gaps=[],decision_comparison={'title':'identity','recommendation':'review','candidates':['A'],'rows':[{'metric':'test','values':['unknown'],'source_ids':['ed9c7a9a,050e188e','deadbeef','ed9c7a9a']}],'reasons':[],'limitations':[],'next_steps':[]})
    out=normalize_source_ids(r,[{'id':a},{'id':b}])
    assert out.decision_comparison.rows[0].source_ids==[a,b,'deadbeef']
    assert r.decision_comparison.rows[0].source_ids[0]=='ed9c7a9a,050e188e'
    ambiguous=normalize_source_ids(r,[{'id':a},{'id':a[:-1]+'5'},{'id':b}])
    assert ambiguous.decision_comparison.rows[0].source_ids==r.decision_comparison.rows[0].source_ids


def test_identity_citation_repair_explains_flat_ids_without_coercing_invalid_output():
    from pydantic import ValidationError
    data={'summary':'test','gaps':[],'decision_comparison':{'title':'test','recommendation':'unknown','candidates':['A'],'rows':[{'metric':x,'values':['unknown'],'source_ids':[['source-1']]} for x in IDENTITY_ROWS],'reasons':[],'limitations':[],'next_steps':[]}}
    try:IdentitySummary.model_validate(data)
    except ValidationError as exc:error=exc
    calls=[];saved=[]
    class Writer:
        async def ainvoke(self,messages):
            calls.append([dict(m) for m in messages])
            return {'raw':None,'parsed':None,'parsing_error':error}
    class Model:
        def with_structured_output(self,*args,**kwargs):return Writer()
    with pytest.raises(ValidationError):
        asyncio.run(recover_stage_one(Model(),[{'id':'source-1','basis':'source','text':'identity'}],{},None,saved.append,lambda *a:None,lambda r,e:(r,[])))
    assert len(calls)==2 and not saved
    payload=json.loads(calls[0][1]['content'])
    assert payload['citation_format']['allowed_source_ids']==['source-1']
    assert payload['citation_format']['example']=={'source_ids':['source-1']}
    assert '一维字符串数组' in calls[1][-1]['content']
    assert '禁止嵌套数组' in calls[1][-1]['content']
