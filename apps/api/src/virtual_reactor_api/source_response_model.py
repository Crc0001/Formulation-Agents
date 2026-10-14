from .table_vision import usable_source, source_notice
"""Source-only empirical response fitting, with explicit units and confounders."""
import json,re,hashlib
import numpy as np
from pydantic import BaseModel,Field
from .capsule_models import EvidenceInput
from .source_metrics import source_numbers

class Point(BaseModel):
    x:float=Field(allow_inf_nan=False)
    y:float=Field(allow_inf_nan=False)
    x_quote:str=Field(min_length=3)
    y_quote:str=Field(min_length=3)
class ResponseInput(BaseModel):
    title:str=Field(min_length=3)
    source_id:str
    locator:str=Field(min_length=2)
    conditions:str=Field(min_length=5)
    x_name:str=Field(min_length=1)
    x_unit:str=Field(min_length=1)
    x_basis:str=Field(min_length=3)
    y_name:str=Field(min_length=1)
    y_unit:str=Field(min_length=1)
    confounders:list[str]=Field(min_length=1)
    points:list[Point]=Field(min_length=3,max_length=100)

def solve(points):
    a=np.asarray(points,dtype=float);x,y=a.T
    if len(np.unique(x))<3:raise ValueError('至少需要三个不同因素水平；重复测量不能冒充不同水平')
    center=float(np.mean(x));scale=float(np.ptp(x));z=(x-center)/scale
    candidates=[]
    for degree in ([1,2] if len(np.unique(x))>=6 else [1]):
        design=np.vander(z,degree+1,increasing=True)
        coefficients=np.linalg.lstsq(design,y,rcond=None)[0];pred=design@coefficients
        held=[]
        for level in np.unique(x):
            train=x!=level;test=~train
            if len(np.unique(x[train]))<=degree:continue
            c=np.linalg.lstsq(design[train],y[train],rcond=None)[0]
            held.extend((design[test]@c-y[test]).tolist())
        candidates.append({'degree':degree,'coefficients':coefficients.tolist(),'fitted':pred.tolist(),'residuals':(pred-y).tolist(),'rmse':float(np.sqrt(np.mean((pred-y)**2))),'internal_level_holdout_rmse':float(np.sqrt(np.mean(np.array(held)**2))) if held else None})
    best=min(candidates,key=lambda c:c['internal_level_holdout_rmse'] if c['internal_level_holdout_rmse'] is not None else float('inf'))
    grid=np.linspace(min(x),max(x),41);prediction=np.polynomial.polynomial.polyval((grid-center)/scale,best['coefficients'])
    return {'models':candidates,'selected_degree':best['degree'],'center':center,'scale':scale,'domain':[float(min(x)),float(max(x))],'curve':list(map(list,zip(grid.tolist(),prediction.tolist()))),'observed':a.tolist(),'selection':'按留一因素水平内部检查误差选择；不足6个水平仅拟合直线。不是独立验证。','equation':'z=(x-center)/scale; y=c0+c1*z'+('+c2*z^2' if best['degree']==2 else ''),'linear_slope':best['coefficients'][1]/scale if best['degree']==1 else None}

def calculate_and_save(store,pid,rid,data):
    if store.run(rid)['project_id']!=pid:raise ValueError('项目不匹配')
    v=ResponseInput.model_validate(data);evidence=store.rows('evidence',pid)
    source=next((e for e in evidence if e['id']==v.source_id),None)
    if not usable_source(source,evidence):raise ValueError('必须使用同一可读原始来源，不能使用假设或摘要线索')
    compact=lambda text:re.sub(r'\s+','',text)
    for p in v.points:
        for number,quote in ((p.x,p.x_quote),(p.y,p.y_quote)):
            if compact(quote) not in compact(source['text']) or number not in source_numbers(quote):raise ValueError('因素或响应数值未通过逐条原文摘录检查；不得猜配比或数字化图点')
    raw=v.model_dump();raw['points']=sorted(raw['points'],key=lambda p:(p['x'],p['y']))
    key=hashlib.sha256(json.dumps(raw,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    for e in evidence:
        if e.get('fields',{}).get('source_response_key')==key:return {'evidence_id':e['id'],'reused':True,'result':json.loads(e['fields']['source_response_model_json'])}
    result={**raw,**solve([[p['x'],p['y']] for p in raw['points']]),'target_prediction':None,'limitations':['来源条件内经验关系；没有识别独立辅料贡献或因果机制。','配比同时改变硬度、孔隙或工艺时斜率包含混杂，不作目标溶出系数。','摘录与数字匹配不能证明表格行列和样品身份正确，需核对。','不外推、不输出置信区间；误差是来源内拟合及内部水平留出。']}
    result['source_reading']=source_notice(source,evidence)
    result['limitations'].append(result['source_reading'])
    saved=store.add_evidence(pid,EvidenceInput(section='comparison',title=v.title,basis='hypothesis',access='imported',text='程序执行的来源响应拟合，非目标预测。'+v.conditions,applicability='仅来源范围，需核对混杂。',fields={'source_response_model_json':json.dumps(result,ensure_ascii=False,allow_nan=False),'source_response_key':key,'source_ids_json':json.dumps([v.source_id])}),rid)
    return {'evidence_id':saved['id'],'reused':False,'result':result}
