"""Execute saved 03 response models in 04, without re-fitting or target adoption."""
import json, math
from copy import deepcopy
from .topic_data_package import digest, citation_ids

FIELDS=('source_response_model_json','source_curve_model_json','pair_difference_model_json')
def package(binding,run,evidence):
    report=run.get('report') or {}
    study=report.get('interaction_research') or {}
    ids=citation_ids(study)
    models=[]
    for e in evidence:
        if e['id'] not in ids:continue
        for key in FIELDS:
            if not e.get('fields',{}).get(key):continue
            try:r=json.loads(e['fields'][key])
            except (ValueError,TypeError):continue
            if not isinstance(r,dict):continue
            models.append({'evidence_id':e['id'],'kind':key,'title':e['title'],'record':r,'source_url':e.get('source_url'),'content_hash':digest(r)})
    value={'schema':'doe-source-package-v1','baseline_id':binding['baseline_id'],'run_id':run['id'],
        'research_target':binding.get('research_target'),'models':models,
        'source_case':study.get('source_case'),'pair_synthesis':study.get('pair_synthesis'),
        'next_research':study.get('next_research'),'scope':'source_conditions_only',
        'target_prediction':None}
    return deepcopy({**value,'version':digest(value)})

def evaluate(model,values):
    if model['kind']!='source_response_model_json':raise ValueError('本条不是连续因素响应模型；保留来源曲线或配对对照，不能插值为用量模型')
    r=model['record'];m=next((m for m in r.get('models',[]) if m.get('degree')==r.get('selected_degree')),None)
    if not m:raise ValueError('缺已选模型参数，返回03补齐')
    lo,hi=r['domain'];scale=r['scale'];center=r['center'];coeff=m['coefficients']
    if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in [lo,hi,scale,center,*coeff]) or scale<=0 or hi<=lo:raise ValueError('模型参数或适用域无效')
    if len(values)<2 or len(values)>21 or any(not math.isfinite(x) or not lo<=x<=hi for x in values):raise ValueError('因素水平须为2–21个有限数值，且全部在来源适用域内')
    result=[[x,sum(c*((x-center)/scale)**i for i,c in enumerate(coeff))] for x in values]
    if any(not math.isfinite(y) for _,y in result):raise ValueError('计算非有限')
    return {'points':result,'change':result[-1][1]-result[0][1], 'x_name':r.get('x_name'),'x_unit':r.get('x_unit'),
      'x_basis':r.get('x_basis'),'y_name':r.get('y_name'),'y_unit':r.get('y_unit'),
      'equation':r.get('equation'),'parameters':{'center':center,'scale':scale,'coefficients':coeff},
      'domain':r['domain'],'conditions':r.get('conditions'),'rmse':m.get('rmse'),
      'holdout_rmse':m.get('internal_level_holdout_rmse'),'confounders':r.get('confounders'),
      'limitations':r.get('limitations'),'scope':'source_conditions_only','target_prediction':None}

def compact(p):
    # Complete numerical models remain available; duplicated historical prose is omitted.
    return {k:v for k,v in p.items() if k not in ('next_research',)}
