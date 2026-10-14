import asyncio
import pytest
import httpx
from openai import APIError, AuthenticationError
from virtual_reactor_api.research_limits import provider_failure
from langchain_core.messages import HumanMessage,AIMessage,ToolMessage
from virtual_reactor_api.research_limits import compact_tool_messages,invoke_with_recovery,interruption_report,is_summary_recovery,report_sources

def test_wrapped_recovery_and_full_source_text_preserved():
    assert is_summary_recovery('【处方辅料筛选】context\n变化方案：{}\n问题：【接续：汇总】整理')
    assert is_summary_recovery('【原研及处方工艺】【接续：汇总】保存资料')
    assert not is_summary_recovery('【原研及处方工艺】新的检索')
    evidence={'id':'e1','title':'table','text':'x'*20000,'basis':'image_estimate','access':'page_text','source_url':'https://example.org','locator':'p3','fields':{'ocr_geometry':'large'}}
    result=report_sources([evidence,evidence])
    assert len(result)==1 and result[0]['text']==evidence['text']
    assert result[0]['basis']=='image_estimate' and 'fields' not in result[0]

def test_timeout_preserves_checkpoint_without_mutating_original():
    draft={'summary':'已有处方','formulations':[{'title':'source example'}],'processes':[{'title':'same example'}],'gaps':['未核实']}
    result=interruption_report([], 'run', 'timeout', draft)
    assert result['formulations']==draft['formulations'] and result['processes']==draft['processes']
    assert 'timeout' in result['gaps'] and draft['gaps']==['未核实']
    assert '中断' in result['summary'] and draft['summary']=='已有处方'

def test_archive_preserves_original_and_call_pair():
    body='BEGIN'+('x'*70000)+'END'
    messages=[HumanMessage('request'),AIMessage(content='',tool_calls=[{'name':'read_source','args':{},'id':'c'}]),ToolMessage(body,tool_call_id='c'),HumanMessage('finish')]
    saved={}
    result,count=compact_tool_messages(messages,lambda p,v:saved.update({p:v}),keep_recent=1)
    assert count==1 and result[2].tool_call_id=='c'
    assert list(saved.values())[0]['content']==body
    assert 'read_file' in result[2].content and len(result[2].content)<2400
    assert messages[2].content==body and result[1]==messages[1]

def test_timeout_recovery_once_and_cancellation_not_retried():
    async def run():
        calls=[];events=[]
        async def invoke(p):
            calls.append(p)
            if p=='initial':raise TimeoutError()
            return 'report'
        assert await invoke_with_recovery(invoke,'initial',lambda:'fresh',lambda:events.append('recovery'))=='report'
        assert calls==['initial','fresh'] and events==['recovery']
        async def fail(p):calls.append(p);raise TimeoutError()
        calls.clear()
        with pytest.raises(TimeoutError):await invoke_with_recovery(fail,'initial',lambda:'fresh',lambda:None)
        assert calls==['initial','fresh']
        async def cancel(p):raise asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError):await invoke_with_recovery(cancel,'initial',lambda:pytest.fail('cancelled should not resume'),lambda:None)
    asyncio.run(run())

def test_provider_error_recovery_and_secret_safe_metadata():
    request=httpx.Request('POST','https://example.test/secret-path')
    error=APIError('secret body',request=request,body={'api_key':'secret'})
    detail=provider_failure(error)
    assert detail['retryable'] and 'secret' not in str(detail)
    auth=AuthenticationError('secret',response=httpx.Response(401,request=request),body=None)
    assert not provider_failure(auth)['retryable']
    assert provider_failure(ValueError('invalid')) is None
    async def run():
        calls=[]
        async def invoke(p):
            calls.append(p)
            if p=='initial':raise error
            return 'recovered'
        assert await invoke_with_recovery(invoke,'initial',lambda:'saved',lambda:None)=='recovered'
        assert calls==['initial','saved']
        async def fail(p):raise auth
        with pytest.raises(AuthenticationError):
            await invoke_with_recovery(fail,'initial',lambda:pytest.fail('auth must not retry'),lambda:None)
        calls.clear()
        async def always(p):calls.append(p);raise error
        with pytest.raises(APIError):await invoke_with_recovery(always,'initial',lambda:'saved',lambda:None)
        assert calls==['initial','saved']
    asyncio.run(run())

def test_empty_stream_is_recoverable_but_validation_errors_are_not():
    error=ValueError('No generations found in stream.')
    assert provider_failure(error)['error_type']=='EmptyModelStream'
    assert provider_failure(ValueError('unknown unit')) is None
    async def run():
        calls=[]
        async def invoke(p):
            calls.append(p)
            if p=='initial':raise error
            return 'saved report'
        assert await invoke_with_recovery(invoke,'initial',lambda:'nonstream',lambda:None)=='saved report'
        assert calls==['initial','nonstream']
    asyncio.run(run())

def test_readerror_is_recoverable_and_interaction_summary_dispatch():
 from httpx import ReadError
 from virtual_reactor_api.research_limits import provider_failure,is_summary_recovery
 assert provider_failure(ReadError('secret transport details'))['retryable']
 assert 'secret' not in str(provider_failure(ReadError('secret transport details')))
 assert is_summary_recovery('【角色：辅料相互作用】\ncontext\n本轮问题：【接续：汇总】整理保存结果')
 assert not is_summary_recovery('【角色：辅料相互作用】\ncontext【接续：汇总】\n本轮问题：新检索')
