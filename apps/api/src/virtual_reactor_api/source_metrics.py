from .table_vision import usable_source, source_notice
"""Traceable scalar source comparisons, independent of target prediction."""
import json,re,math
from pydantic import Field
from typing import Literal
from .capsule_models import Model,EvidenceInput
class MetricPoint(Model):
    label:str=Field(min_length=1)
    value:float
    quote:str=Field(min_length=8)
class SourceMetric(Model):
    title:str=Field(min_length=1)
    unit:str=Field(min_length=1)
    source_id:str
    locator:str=Field(min_length=1)
    conditions:str=Field(min_length=1)
    limitations:str=Field(min_length=1)
    source_reading:str=''
    quantity:Literal['scalar','ribbon_solid_fraction']='scalar'
    points:list[MetricPoint]=Field(min_length=2,max_length=20)
def source_numbers(text):
    # A sentence-ending period is punctuation, not a continuation of a decimal.
    # Refuse partial matches inside identifiers, version numbers or comma-formatted numbers.
    pattern=r'(?<![\w.,+−-])[+-]?(?:\d+\.\d+|\d+|\.\d+)(?:[eE][+-]?\d+)?(?![\w]|\.\d|,\d)'
    return [float(x) for x in re.findall(pattern,text.replace('−','-'))]

def structure_calculation(solid_fractions):
    porosities=[1-s for s in solid_fractions]
    factors=[e**3/(1-e)**2 for e in porosities]
    return {'model_id':'ribbon-porosity-geometry-v1','porosity':porosities,
      'porosity_change_pp':[100*(e-porosities[0]) for e in porosities],
      'geometry_factor':factors,'geometry_factor_ratio':[g/factors[0] for g in factors],
      'equations':['epsilon = 1 - solid_fraction','G(epsilon) = epsilon^3/(1-epsilon)^2','k1/k0 = (G1/G0)*(K0_base/K0_new)*(Sv_base/Sv_new)^2'],
      'status':'来源压带结构复算及条件几何因子，不是目标性能预测',
      'limitations':['孔隙率由作者概括的压带固相分数推算，不是另一次孔隙率实测。','Kozeny–Carman几何因子不等于渗透率；只有比表面积Sv及形状/曲折参数K0不变且模型适用时，该因子比才等于渗透率比。','来源压带、整粒后颗粒与胶囊填充床属于不同结构，不直接转成目标床孔隙、进液或溶出。','未对淀粉用量拟合通用系数，不外推至当前MCC补差处方。']}

def validate_metric(data,evidence):
    metric=SourceMetric.model_validate(data)
    source=next((e for e in evidence if e['id']==metric.source_id),None)
    if not usable_source(source,evidence):
        raise ValueError('图示必须绑定已取得的原始来源，不能使用搜索摘要或模型假设')
    compact=lambda s:re.sub(r'\s+','',s)
    text=compact(source['text'])
    if len({p.label for p in metric.points})!=len(metric.points):raise ValueError('组名重复')
    for point in metric.points:
        if compact(point.quote) not in text:raise ValueError('逐组原文摘录未在绑定来源中找到')
        numbers=source_numbers(point.quote)
        if point.value not in numbers:raise ValueError('逐组数值未在对应摘录中找到')
    result=metric.model_dump()
    result['source_reading']=source_notice(source,evidence)
    if result['source_reading'] not in result['limitations']:result['limitations']+='；'+result['source_reading']
    if metric.quantity=='ribbon_solid_fraction':
        if metric.unit!='1' or any(not 0<p.value<1 for p in metric.points):raise ValueError('压带固相分数必须使用无量纲0到1之间的值')
        result['structure_calculation']=structure_calculation([p.value for p in metric.points])
    return result
def save_metric(store,pid,run_id,data):
    if run_id and store.run(run_id)['project_id']!=pid:raise ValueError('项目不匹配')
    value=validate_metric(data,store.rows('evidence',pid))
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False)
    for e in store.rows('evidence',pid):
        if e.get('fields',{}).get('source_metric_json')==raw:return e
    return store.add_evidence(pid,EvidenceInput(section='comparison',title=value['title'],basis='hypothesis',access='imported',text='原文数值图示整理；非目标处方预测。'+value['conditions'],applicability=value['limitations'],fields={'source_metric_json':raw,'source_ids_json':json.dumps([value['source_id']])}),run_id)
