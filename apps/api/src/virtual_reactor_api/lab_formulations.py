"""Versioned laboratory formulation datasets; no automatic fitting or imputation."""
import math
from typing import Literal
from pydantic import Field,model_validator
from .capsule_models import Model

class LabMaterial(Model):
    name:str=Field(min_length=1)
    role:Literal['api','excipient']
    amount:float=Field(ge=0,allow_inf_nan=False)
    unit:Literal['mg/unit','g/batch','parts','%w/w']
    manufacturer:str=''
    grade:str=''
    batch:str=''
    property_record_id:str=''
class Response(Model):
    metric:str=Field(min_length=1)
    value:float=Field(allow_inf_nan=False)
    unit:str=Field(min_length=1)
    time_min:float|None=Field(default=None,ge=0,allow_inf_nan=False)
    replicate:str=''
    method:str=''
class Trial(Model):
    trial_id:str=Field(min_length=1)
    batch_id:str=Field(min_length=1)
    materials:list[LabMaterial]=Field(min_length=2)
    process:str=Field(min_length=1)
    responses:list[Response]=Field(min_length=1)
    intended_use:Literal['unassigned','training','validation']='unassigned'
    @model_validator(mode='after')
    def identities(self):
        if not any(m.role=='api' for m in self.materials):raise ValueError('每个制剂试验须列明API')
        if len({m.name for m in self.materials})!=len(self.materials):raise ValueError('同一试验物料名称重复')
        if len({m.unit for m in self.materials})!=1:raise ValueError('同一试验的投料单位必须统一，不能混合百分比和mg')
        return self
class LabDataset(Model):
    title:str=Field(min_length=1)
    api_identity:str=Field(min_length=1)
    dosage_form:str=Field(min_length=1)
    provenance:str=Field(min_length=1)
    trials:list[Trial]=Field(min_length=1,max_length=5000)
    @model_validator(mode='after')
    def unique(self):
        if len({t.trial_id for t in self.trials})!=len(self.trials):raise ValueError('试验编号重复')
        batches={}
        for t in self.trials:
            batches.setdefault(t.batch_id,set()).add(t.intended_use)
        if any('training' in v and 'validation' in v for v in batches.values()):raise ValueError('同一批次不能同时分到训练和验证')
        return self
class ResearchCase(Model):
    title:str=Field(min_length=1)
    mode:Literal['literature','laboratory']
    materials:list[str]=Field(min_length=1,max_length=2)
    objective:str=Field(min_length=3)
    dosage_form:str='待选来源制剂'
    dataset_id:str|None=None
    @model_validator(mode='after')
    def scope(self):
        self.materials=[x.strip() for x in self.materials]
        if any(not x for x in self.materials) or len(set(self.materials))!=len(self.materials):raise ValueError('研究物料须非空且不重复')
        if self.mode=='laboratory' and not self.dataset_id:raise ValueError('实验室模式请先选择已导入的制剂实验数据包')
        if self.mode=='literature' and self.dataset_id:raise ValueError('文献模式不绑定实验室数据包')
        return self

def context(case,dataset=None):
    return {'id':case['id'],'title':case['title'],'research_mode':case['mode'],
        'ingredients':[{'id':'case-material-'+str(i+1),'name':name,'role':'excipient','amount_mg':None,'brand':'','grade':'','particle':''} for i,name in enumerate(case['materials'])],
        'process':'由来源案例核对，未指定目标处方工艺','api_particle':'待来源核对','mass_basis':'研究物料目录，非定量处方',
        'source_ids':[dataset['evidence_id']] if dataset else [],'dataset_id':case.get('dataset_id'),
        'api_identity':dataset['api_identity'] if dataset else '由文献选案确定，不继承所在项目药物',
        'dosage_form':dataset['dosage_form'] if dataset else case['dosage_form']}
