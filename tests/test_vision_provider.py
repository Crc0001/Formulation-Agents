import asyncio,base64,io,json
from types import SimpleNamespace
import pytest
from PIL import Image
from pydantic import BaseModel
from virtual_reactor_api.vision_provider import McpVision,VisionReader,VisionProviderError,parse_output,image_input,vision_model
class Result(BaseModel):
    code:str

def picture():
    b=io.BytesIO();Image.new('RGB',(50,30),'white').save(b,format='PNG')
    return [{'role':'user','content':[{'type':'text','text':'read image'},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()}}]}]

def test_glm_missing_config_fails_closed(tmp_path):
    with pytest.raises(VisionProviderError):vision_model(tmp_path,SimpleNamespace(generatorModel='openai:glm-5.3'))

def test_gpt_retains_existing_model(monkeypatch,tmp_path):
    from virtual_reactor_api import agent_runtime
    calls=[];monkeypatch.setattr(agent_runtime,'_create_model',lambda *args:calls.append(args) or 'gpt')
    assert vision_model(tmp_path,SimpleNamespace(generatorModel='openai:gpt-6-astra',generatorApiKey='private',generatorBaseUrl='https://example.org'))=='gpt'
    assert calls==[('openai:gpt-6-astra','private','https://example.org')]

def test_strict_output_no_fabricated_fields():
    assert parse_output('```json\n{"code":"18.45"}\n```',Result).code=='18.45'
    for text in ['{}','not json','{"code":null}','secret response is not valid']:
        with pytest.raises(VisionProviderError,match='VisionInvalidStructuredOutput'):parse_output(text,Result)

@pytest.mark.parametrize('url',['https://example.org/private.png','file:///C:/secret.txt','data:text/plain;base64,YQ=='])
def test_only_embedded_valid_images(url):
    m=picture();m[0]['content'][1]['image_url']['url']=url
    with pytest.raises(VisionProviderError):image_input(m)

@pytest.mark.parametrize('schema_name,tool',[('Result','extract_text_from_screenshot'),('Geometry','analyze_data_visualization')])
def test_mcp_tool_choice_and_temp_cleanup(tmp_path,schema_name,tool):
    calls=[]
    class Schema(BaseModel):code:str
    Schema.__name__=schema_name
    class Model:
        root=tmp_path
        async def call(self,req):
            calls.append(req)
            from pathlib import Path
            assert Path(req['image_path']).is_file()
            return {'text':'{"code":"18.45"}'}
    result=asyncio.run(VisionReader(Model(),Schema).ainvoke(picture()))
    assert result.code=='18.45' and calls[0]['tool']==tool
    assert not list((tmp_path/'workspace/vision-mcp').iterdir())

def test_mcp_error_cleans_image_without_fallback(tmp_path):
    class Model:
        root=tmp_path
        async def call(self,request):raise VisionProviderError('VisionProviderError')
    with pytest.raises(VisionProviderError):asyncio.run(VisionReader(Model(),Result).ainvoke(picture()))
    assert not list((tmp_path/'workspace/vision-mcp').iterdir())
