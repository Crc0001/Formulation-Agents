"""Server-only credentials, frozen per task; never mutate process environment."""
from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import replace
import tomllib

CHOICES={'astra':('GPT Astra','astra.local.toml'),'glm':('GLM-5.3','glm.local.toml')}
selected_generator=ContextVar('selected_generator',default=None)

def resolve(root,profile_id):
    if profile_id not in CHOICES:raise ValueError('请选择已有模型')
    label,filename=CHOICES[profile_id]
    try:
        value=tomllib.loads((root/'config'/filename).read_text(encoding='utf-8-sig'))['generator']
        if not all(isinstance(value.get(k),str) and value[k].strip() for k in ('model','api_key','base_url')):raise ValueError()
    except Exception:raise ValueError(label+'的服务端接口配置不完整') from None
    return {'profile_id':profile_id,'label':label,**{k:value[k] for k in ('model','api_key','base_url')}}

def public_profiles(root):
    result=[]
    for pid,(label,_) in CHOICES.items():
        try:
            value=resolve(root,pid);result.append({'id':pid,'label':label,'model':value['model'],'configured':True})
        except ValueError:result.append({'id':pid,'label':label,'configured':False})
    return result

@contextmanager
def using_profile(value):
    token=selected_generator.set(value)
    try:yield
    finally:selected_generator.reset(token)

def apply_profile(settings):
    value=selected_generator.get()
    if value is None:return settings
    return replace(settings,generatorModel=value['model'],generatorApiKey=value['api_key'],generatorBaseUrl=value['base_url'])
