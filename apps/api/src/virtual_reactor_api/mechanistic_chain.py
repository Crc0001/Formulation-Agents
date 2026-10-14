"""Versioned local capillary-exposure / shrinking-sphere model; not a calibrated formulation predictor."""
import math,json,re
from pydantic import Field
from typing import Literal
from .capsule_models import Model,EvidenceInput
MODEL_ID='capillary-sphere-sink-v1'
UNITS={'permeability':'m2','surface_tension':'N/m','contact_angle':'deg','viscosity':'Pa.s','porosity':'1','pore_radius':'m','path_length':'m','diffusivity':'m2/s','solubility':'kg/m3','api_density':'kg/m3','diffusion_layer':'m','api_diameter':'m','medium_volume':'m3','shell_lag':'s'}
class Parameter(Model):
 value:float
 unit:str
 basis:Literal['source','measurement','explicit_hypothesis']
 source_id:str=Field(min_length=1)
 locator:str=Field(min_length=1)
 applicability:str=Field(min_length=1)
 source_quote:str=''
class Arm(Model):
 label:str
 parameters:dict[str,Parameter]
class ChainInput(Model):
 baseline_id:str
 variant_id:str
 mass_basis:str=Field(min_length=1)
 assumptions:str=Field(min_length=20)
 arms:list[Arm]=Field(min_length=2,max_length=2)
 times_s:list[float]=Field(min_length=2,max_length=500)

def frozen_pair(message):
 decoder=json.JSONDecoder()
 base=decoder.raw_decode(message.split('冻结基准：',1)[1])[0]
 variant=decoder.raw_decode(message.split('变化方案：',1)[1])[0]
 return base,variant

def solve(data,base,variant,n=128):
 from scipy.special import roots_legendre
 value=ChainInput.model_validate(data)
 if (value.baseline_id,value.variant_id)!=(base['id'],variant['id']):raise ValueError('计算必须绑定本轮冻结基准和变化方案')
 api=[i for i in base['ingredients'] if i['role']=='api']
 api1=[i for i in variant['ingredients'] if i['role']=='api']
 if len(api)!=1 or api!=api1:raise ValueError('两臂API必须保持身份、用量及规格不变')
 m0=api[0]['amount_mg']*1e-6
 if not math.isfinite(m0) or m0<=0:raise ValueError('API质量无效')
 t=value.times_s
 if t[0]<0 or any(b<=a for a,b in zip(t,t[1:])) or not all(math.isfinite(x) for x in t):raise ValueError('时间必须有限、非负且严格递增')
 nodes,weights=roots_legendre(n);nodes=(nodes+1)/2;weights=weights/2
 results=[]
 for arm in value.arms:
  if set(arm.parameters)!=set(UNITS):raise ValueError('物理参数必须齐全：'+', '.join(sorted(set(UNITS)-set(arm.parameters))))
  for key,p in arm.parameters.items():
   if p.unit!=UNITS[key]:raise ValueError(key+'单位应为'+UNITS[key])
  p={k:v.value for k,v in arm.parameters.items()}
  if any(v<=0 for k,v in p.items() if k not in ('contact_angle','shell_lag')) or p['shell_lag']<0 or not 0<=p['contact_angle']<90 or not 0<p['porosity']<1:raise ValueError('参数超出适用域；接触角≥90°时不能用自发毛细进液模型画零溶出曲线')
  capacity=p['solubility']*p['medium_volume']/m0
  if capacity<10:raise ValueError('此版本仅作近似漏槽计算，要求Cs·V/M0≥10；非漏槽须使用有限介质耦合求解器')
  B=4*p['permeability']*p['surface_tension']*math.cos(math.radians(p['contact_angle']))/(p['viscosity']*p['porosity']*p['pore_radius'])
  tw=p['path_length']**2/B
  td=p['api_density']*p['diffusion_layer']*p['api_diameter']/(2*p['diffusivity']*p['solubility'])
  if not all(math.isfinite(x) and x>0 for x in (B,tw,td,capacity)):raise ValueError('物理参数组合超出数值可计算范围')
  q=[];wet=[]
  for time in t:
   elapsed=max(0,time-p['shell_lag']);front=min(1,math.sqrt(elapsed/tw));wet.append(100*front)
   # Integrate uniformly distributed depth, splitting where particles completely dissolve.
   complete=min(front,math.sqrt(max(0,elapsed-td)/tw))
   u=complete+(front-complete)*nodes
   ages=elapsed-tw*u*u
   dissolved=1-(1-ages/td).clip(0,1)**3
   q.append(100*float(complete+(front-complete)*sum(weights*dissolved)))
  results.append({'label':arm.label,'B_m2_s':B,'wetting_time_s':tw,'particle_dissolution_time_s':td,'sink_capacity_ratio':capacity,'wet_percent':wet,'dissolved_percent':q,'undissolved_percent':[100-x for x in q]})
 return {'model_id':MODEL_ID,'status':'未校准机理条件计算，非目标验证预测','input':value.model_dump(),'baseline_snapshot':base,'variant_snapshot':variant,'time_s':t,'arms':results,'delta_percent_points':[b-a for a,b in zip(results[0]['dissolved_percent'],results[1]['dissolved_percent'])],'limitations':['均匀刚性等效平板、单向进液、固定孔隙及润湿参数；不适用于未建模的显著膨胀或破碎。','暴露即成为可接触的致密单分散API球；不包括持续黏结、团聚和再团聚。','近似漏槽且扩散层固定，无化学反应、晶型转化或微环境pH漂移；Cs和API称量必须同一质量基准。','处方到制粒后孔隙/渗透率/接触角的映射需来源或目标测量，不能由原粉用量直接推定。','数值求解与质量守恒不等于药学有效；目标实验确认前不能判断等效或优胜。']}

def calculate_and_save(store,pid,run_id,data):
 run=store.run(run_id)
 if run['project_id']!=pid:raise ValueError('项目不匹配')
 base,variant=frozen_pair(run['message'])
 value=ChainInput.model_validate(data)
 sources={e['id']:e for e in store.rows('evidence',pid)}
 for arm in value.arms:
  for p in arm.parameters.values():
   e=sources.get(p.source_id)
   if not e or e['access'] not in ('full_text','page_text','imported','user') or e['basis'] in ('search_lead','unknown'):raise ValueError('参数必须有本项目归档依据')
   if p.basis!='explicit_hypothesis':
    if e['basis'] not in ('source','measurement'):raise ValueError('假设证据不能冒充来源参数或实测')
    normalize=lambda text:re.sub(r'\s+','',text)
    if len(p.source_quote)<8 or normalize(p.source_quote) not in normalize(e['text']):raise ValueError('来源参数须提供可核对的逐字摘录；SI换算在适用说明中保留')
 result=solve(data,base,variant)
 return store.add_evidence(pid,EvidenceInput(section='comparison',title='机理条件计算 · '+variant['title'],basis='hypothesis',access='imported',text=result['status'],applicability='；'.join(result['limitations']),fields={'mechanistic_chain_json':json.dumps(result,ensure_ascii=False,allow_nan=False)}),run_id),result
