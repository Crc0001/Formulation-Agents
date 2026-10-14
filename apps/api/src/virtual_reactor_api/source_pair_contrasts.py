from .table_vision import usable_source
"""Observed within-source contrasts; no fitted dose curve or target transfer."""
import json, math
from pydantic import Field
from .capsule_models import Model, EvidenceInput
from .source_metrics import validate_metric, source_numbers

class Mixture(Model):
    changing_material: str = Field(min_length=1)
    balancing_material: str = Field(min_length=1)
    amount_unit: str = Field(min_length=1)
    changing_before: float = Field(ge=0)
    changing_after: float = Field(ge=0)
    balancing_before: float = Field(ge=0)
    balancing_after: float = Field(ge=0)

class Contrast(Model):
    mixture: Mixture | None = None
    before_label: str
    after_label: str
    conditions: str = Field(min_length=5)
    comparison_basis: str = Field(min_length=8)
    basis_source_id: str
    basis_quote: str = Field(min_length=8)

class ContrastInput(Model):
    metric_id: str
    pairs: list[Contrast] = Field(min_length=1, max_length=10)

def calculate(data, evidence):
    spec=ContrastInput.model_validate(data)
    refs={e['id']:e for e in evidence}
    saved=refs.get(spec.metric_id, {})
    if saved.get('basis')!='hypothesis': raise ValueError('必须引用已保存的来源数值记录')
    metric=json.loads(saved.get('fields',{}).get('source_metric_json','null'))
    if not metric: raise ValueError('未找到来源数值记录')
    metric=validate_metric(metric,evidence)
    points={p['label']:p for p in metric['points']}
    result=[]; seen=set()
    compact=lambda t: ''.join(t.split())
    for pair in spec.pairs:
        key=(pair.before_label,pair.after_label)
        if key in seen or key[0]==key[1]: raise ValueError('配对重复或两侧相同')
        seen.add(key)
        if any(k not in points for k in key): raise ValueError('样品名必须精确对应来源记录')
        basis=refs.get(pair.basis_source_id,{})
        if not usable_source(basis,evidence):
            raise ValueError('配对条件须绑定可读原文')
        if compact(pair.basis_quote) not in compact(basis.get('text','')):
            raise ValueError('配对依据摘录未找到')
        if pair.mixture:
            m=pair.mixture
            values=[m.changing_before,m.changing_after,m.balancing_before,m.balancing_after]
            if not all(math.isfinite(v) for v in values): raise ValueError('配对用量必须有限')
            if m.changing_material==m.balancing_material: raise ValueError('变化与补差须为不同物料')
            total=m.changing_before+m.balancing_before
            if total<=0 or not math.isclose(total,m.changing_after+m.balancing_after,rel_tol=1e-9,abs_tol=1e-9):
                raise ValueError('配对模拟要求两物料合计量固定且大于0')
            if m.changing_before==m.changing_after: raise ValueError('两端组成相同，不能模拟配比变化')
            nums=source_numbers(pair.basis_quote)
            # A missing table cell is not evidence of zero. Require explicit absence declaration.
            for v in values:
                if v!=0 and v not in nums: raise ValueError('组成用量未在条件原文找到')
            if 0 in values and '0' not in pair.comparison_basis: raise ValueError('零用量须在核对说明中明确声明')
        a,b=(points[k]['value'] for k in key)
        if not all(math.isfinite(v) for v in (a,b)): raise ValueError('数值必须有限')
        result.append({**pair.model_dump(),'before':a,'after':b,'difference':b-a,
            'relative_change_percent':100*(b-a)/a if a!=0 else None,
            'direction':'升高' if b>a else '降低' if b<a else '不变'})
    return {'version':'source-endpoint-contrast-v1','metric_id':spec.metric_id,
        'title':metric['title'],'unit':metric['unit'],'source_id':metric['source_id'],
        'metric_snapshot':metric,'pairs':result,'input':spec.model_dump(),
        'equations':['差值 = 后组 − 前组','相对变化(%) = 100 × (后组 − 前组) / 前组；前组为0时不计算'],
        'source_status':'来源端点差异已计算','target_status':'尚未建立目标迁移模型',
        'target_prediction':None,'limitations':[
            metric['limitations'],
            '仅计算指定两组的观察差异；不拟合连续剂量曲线，不分解独立辅料贡献。',
            '各条件分组独立阅读；不同黏合剂、工艺或检测方法不合并为一个系数。',
            '未计算统计显著性或置信区间，差值方向不等于已证实的因果关系。',
            '原文摘录校验不代替样品列、补差及其它共变条件的科学核对。']}

def save_contrasts(store,pid,run_id,data):
    if run_id and store.run(run_id)['project_id']!=pid: raise ValueError('项目不匹配')
    result=calculate(data,store.rows('evidence',pid))
    raw=json.dumps(result,ensure_ascii=False,sort_keys=True,allow_nan=False)
    for e in store.rows('evidence',pid):
        if e.get('fields',{}).get('pair_difference_model_json')==raw:return e,result
    e=store.add_evidence(pid,EvidenceInput(section='comparison',title='来源配对差异：'+result['title'],
        basis='hypothesis',access='imported',text=result['source_status']+'；'+result['target_status'],
        applicability='；'.join(result['limitations']),fields={'pair_difference_model_json':raw}),run_id)
    return e,result
