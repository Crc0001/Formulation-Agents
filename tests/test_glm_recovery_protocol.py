import pytest
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from virtual_reactor_api.agent_runtime import _create_model
from virtual_reactor_api.capsule_research import report_recovery_model

@pytest.mark.parametrize('phase',[1,2,3,None])
def test_glm_recovery_stays_chat_completions(phase):
    original=_create_model('openai:glm-5.2','test-no-network','https://example.org/api/paas/v4')
    model=report_recovery_model(original,'openai:glm-5.2',is_origin=phase is not None,origin_phase=phase)
    payload=model._get_request_payload([HumanMessage(content='test')])
    assert model._use_responses_api(payload) is False
    assert 'messages' in payload and 'input' not in payload and 'reasoning' not in payload
    assert model.streaming is True and original.streaming is True
    class Result(BaseModel):
        answer:str
    bound=model.with_structured_output(Result,method='function_calling')
    binding=bound.steps[0]
    structured=model._get_request_payload([HumanMessage(content='test')],**binding.kwargs)
    assert not model._use_responses_api(structured)
    assert 'tools' in structured

def test_astra_recovery_keeps_responses_and_low_effort():
    original=_create_model('openai:gpt-6-astra','test-no-network','https://example.org/v1')
    model=report_recovery_model(original,'openai:gpt-6-astra',is_origin=True,origin_phase=1)
    payload=model._get_request_payload([HumanMessage(content='test')])
    assert model._use_responses_api(payload) and model.reasoning=={'effort':'low'}
    assert original.reasoning=={'effort':'medium'}

def test_anthropic_recovery_does_not_add_openai_reasoning():
    model=_create_model('anthropic:glm-5.2','test-no-network','https://example.org')
    result=report_recovery_model(model,'anthropic:glm-5.2',is_origin=True,origin_phase=2)
    assert result.streaming is False and result.max_tokens==12000
    assert 'reasoning' not in result.__dict__


def test_glm_bigmodel_ignores_os_proxy_but_other_hosts_keep_default():
    model=_create_model('openai:glm-5.2','test-no-network','https://open.bigmodel.cn/api/paas/v4')
    assert model.root_client._client._trust_env is False
    assert model.root_async_client._client._trust_env is False
    import ssl
    assert model.root_async_client._client._transport._pool._ssl_context.verify_mode==ssl.CERT_REQUIRED
    other=_create_model('openai:glm-5.2','test-no-network','https://example.org/v1')
    assert other.root_async_client._client._trust_env is True
