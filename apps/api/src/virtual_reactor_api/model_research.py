"""Versioned research design, not an automatic model-validity certificate."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Record(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False,str_strip_whitespace=True)

class Hypothesis(Record):
    id:str
    title:str
    kind:Literal['empirical','mechanistic','hybrid']
    equation:str
    mapping:str
    parameters:str
    domain:str
    source_ids:list[str]=Field(default_factory=list)
    calibration:str
    holdout:str
    falsifier:str
    status:Literal['proposed','source_computed','target_conditional']='proposed'

class Candidate(Record):
    name:str
    identity:str
    changes:str
    decision:Literal['priority_anchor','retain','defer']
    rationale:str
    reversal:str

class Prediction(Record):
    model_id:str
    value:float
    calculation_evidence_id:str

class DiscriminatingAnchor(Record):
    id:str
    condition:str
    observable:str
    unit:str
    purpose:Literal['calibration','validation','discrimination']
    predictions:list[Prediction]=Field(default_factory=list)
    measurement_sd:float|None=Field(default=None,gt=0)
    sd_source_id:str|None=None
    qualitative_predictions:str
    decision_rule:str
    priority_reason:str

class ResearchDesign(Record):
    version:Literal['model-led-v1']='model-led-v1'
    question:str
    scope:str
    hypotheses:list[Hypothesis]=Field(default_factory=list)
    candidates:list[Candidate]=Field(default_factory=list)
    anchors:list[DiscriminatingAnchor]=Field(default_factory=list)
    next_research:list[str]=Field(default_factory=list)
    @model_validator(mode='after')
    def identities(self):
        ids=[m.id for m in self.hypotheses]
        if len(ids)!=len(set(ids)):raise ValueError('模型ID重复')
        if len({a.id for a in self.anchors})!=len(self.anchors):raise ValueError('锚点ID重复')
        for a in self.anchors:
            pred=[p.model_id for p in a.predictions]
            if len(set(pred))!=len(pred) or any(p not in ids for p in pred):raise ValueError('锚点模型ID重复或不存在')
        return self

def audit_design(design,evidence):
    if not design:return {'status':'未交付模型研究包','issues':[],'anchors':[]}
    d=ResearchDesign.model_validate(design)
    sources={e['id']:e for e in evidence}
    issues=[];result=[]
    readable=lambda sid:sid in sources and sources[sid].get('access') in ('full_text','page_text','imported','user')
    for h in d.hypotheses:
        if not h.source_ids or any(not readable(s) for s in h.source_ids):issues.append(h.title+'：来源依据未完整绑定')
        if not all([h.equation,h.mapping,h.parameters,h.domain,h.falsifier]):issues.append(h.title+'：机理或判别条件不完整')
    for a in d.anchors:
        valid=[p for p in a.predictions if readable(p.calculation_evidence_id) and sources[p.calculation_evidence_id].get('basis')=='hypothesis']
        if len(valid)!=len(a.predictions):issues.append(a.id+'：数值预测缺可读取的计算证据，未计入分歧')
        spread=max(p.value for p in valid)-min(p.value for p in valid) if len(valid)>=2 else None
        normalized=spread/a.measurement_sd if spread is not None and a.measurement_sd and readable(a.sd_source_id) and sources[a.sd_source_id].get('basis') in ('source','measurement') else None
        result.append({'id':a.id,'spread':spread,'normalized_separation':normalized,'unit':a.unit,'status':'计算记录待人工核对；非机理成立证明' if spread is not None else ('仅一个有计算依据的模型，不能计算模型间分歧' if len(valid)==1 else '定性设计，未计算数值分歧')})
    return {'status':'结构化研究设计，未自动采纳','issues':issues,'anchors':result}
