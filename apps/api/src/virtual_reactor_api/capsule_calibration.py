"""A withheld user reference; compare each retrieved formulation independently."""
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException
from .capsule_models import CalibrationReference, FormulaComponent, RetrievedFormula, FormulaComparison, ComparisonRow, CalibrationEvaluation
from .capsule_store import now

ALIASES={
 '盐酸氟桂利嗪':['盐酸氟桂利嗪','氟桂利嗪二盐酸盐','flunarizine hydrochloride','flunarizine dihydrochloride','flunarizina diclorhidrato'],
 '氟桂利嗪':['氟桂利嗪','flunarizine','flunarizina'],
 '玉米淀粉':['玉米淀粉','corn starch','maize starch','starch maize','almidon de maiz'],
 '乳糖':['乳糖','lactose','lactose monohydrate','一水乳糖','lactosa','lactosa monohidrato'],
 '二氧化硅':['二氧化硅','胶态二氧化硅','胶态无水二氧化硅','silicon dioxide','colloidal silicon dioxide','silica','colloidal anhydrous silica','silica colloidal anhydrous','无水胶态二氧化硅','dioxido de silicio'],
 '滑石粉':['滑石粉','滑石','talc','talcum','talco'],
 '硬脂酸镁':['硬脂酸镁','magnesium stearate','estearato de magnesio'],
 '硬脂酸':['硬脂酸','stearic acid','acido estearico'],
 '十二烷基硫酸钠':['十二烷基硫酸钠','月桂醇硫酸钠','sodium lauryl sulfate','sodium lauryl sulphate','sls'],
}

def normalized(value):
    import unicodedata
    text=''.join(c for c in unicodedata.normalize('NFKD',value).casefold() if not unicodedata.combining(c))
    return re.sub(r'[\s()（）,，·\-]+','',text)

def identity(name):
    # Match the ingredient name separately from an explanatory parenthesis.
    base=re.split(r'[（(]',name,maxsplit=1)[0].strip().replace('®','')
    key=normalized(base)
    for canonical,names in ALIASES.items():
        if key in {normalized(n) for n in names}: return canonical
    # Recognize a declared grade suffix, without treating stearic acid as its salt.
    if re.fullmatch(r'(乳糖|lactose)(80\s*(目|mesh)|\s*GranuLac\s*(70|200))?',base,re.I): return '乳糖'
    if key=='aerosil':return '二氧化硅'
    return key

def reference_path(root,pid):
    if pid!='flunarizine-cn-5-calibration': raise HTTPException(404,'该项目尚未设置校准基准')
    return root/'reference/flunarizine-calibration/reference.json'

def load_reference(root,pid):
    raw=json.loads(reference_path(root,pid).read_text(encoding='utf-8'))
    original=reference_path(root,pid).with_name('user-formulation.png')
    if hashlib.sha256(original.read_bytes()).hexdigest()!=raw['sha256']:
        raise ValueError('原始处方截图与归档校验值不符')
    case={k:raw[k] for k in CalibrationReference.model_fields if k in raw}
    case['components']=[FormulaComponent(name=c['name'],compartment=c['compartment'],amount_mg=c['amount_mg'],percent=c['percent'],grade=c['grade'],amount_basis=c['basis'],locator='用户原图表8-1-1；润滑剂名称以用户最新更正为准') for c in raw['components']]
    case['image_url']=f'/api/capsule/projects/{pid}/calibration/image'
    case['source_note']='用户确认这是实际使用且BE符合要求的处方；本程序尚未读取BE原始报告作独立审核。厂家、品牌及是否原研未确认。基准独立保存，不进入检索智能体的工作区或模型上下文。'
    result=CalibrationReference(**case)
    if sum(Decimal(str(c.amount_mg)) for c in result.components)!=Decimal(str(result.fill_mass_mg)):
        raise ValueError('基准处方总量不一致')
    return result

def compare_formula(reference:CalibrationReference,formula:RetrievedFormula,valid_source_ids:set[str]):
    eligible=formula.dosage_form=='capsule' and formula.strength_basis==reference.strength_basis and formula.strength_mg==reference.strength_mg
    source_valid=bool(formula.source_ids) and all(s in valid_source_ids for s in formula.source_ids)
    eligible=eligible and source_valid
    rows=[];used=set()
    for ref in reference.components:
        matches=[(i,c) for i,c in enumerate(formula.components) if identity(c.name)==identity(ref.name)]
        found=next(((i,c) for i,c in matches if c.compartment=='fill'),matches[0] if matches else None)
        value=None;grade='';status='not_found';note='该来源未检出，不能据此认定实际处方不含该辅料。'
        if found:
            i,c=found;used.add(i);grade=c.grade;value=c.amount_mg
            fills=[(j,x) for j,x in matches if x.compartment=='fill']
            if len(fills)>1:
                used.update(j for j,_ in fills)
                same_basis=len({x.amount_basis for _,x in fills})==1
                value=float(sum(Decimal(str(x.amount_mg)) for _,x in fills)) if same_basis and all(x.amount_mg is not None for _,x in fills) else None
                grade='；'.join(x.grade for _,x in fills if x.grade)
                c=c.model_copy(update={'amount_mg':value,'grade':grade,'amount_basis':c.amount_basis if same_basis else 'unknown'})
            if c.compartment!='fill':status='compartment_mismatch';note='成分归属胶囊壳或未知，不能当作填充物命中。'
            elif not eligible or c.amount_basis!=ref.amount_basis:status='basis_mismatch';note='剂型、标示规格、盐/活性成分基准或原文引用尚不一致；保留原值，不换算套用。'
            elif c.amount_mg is None:status='amount_unknown';note='检出成分名称，但公开用量未取得。'
            elif abs(Decimal(str(c.amount_mg))-Decimal(str(ref.amount_mg)))<=Decimal('0.005'):status='matched';note='每粒文档数值在0.01 mg显示精度内一致；不是药学或临床一致结论。'
            else:status='different';note='公开处方数值不同，可能属于不同产品/版本，不能自动判为程序错误。'
            if len(fills)>1:note+=' 同一来源/同一实施例的同名成分已合计，不合并其物理等级。'
        # Grade equality is deliberately stricter than ingredient-family matching.
        grade_status='待核验'
        if identity(ref.name)=='乳糖':
            grade_status='80目有文字命中' if re.search(r'80\s*(目|mesh)',grade,re.I) else '未确认80目'
        rows.append(ComparisonRow(name=ref.name,reference_mg=ref.amount_mg,retrieved_mg=value,status=status,reference_grade=ref.grade,retrieved_grade=grade,grade_status=grade_status,note=note))
    basis_label={'salt':'按盐计','active_moiety':'按活性部分计','unknown':'标示基准未知'}[formula.strength_basis]
    return FormulaComparison(title=formula.title,source_ids=formula.source_ids,scope=f'{formula.product} · {formula.dosage_form} · {formula.strength_mg if formula.strength_mg is not None else "规格未知"} mg（{basis_label}） · {formula.source_role}',eligible_for_amount_comparison=eligible,rows=rows,extra_components=[c.name for i,c in enumerate(formula.components) if i not in used and c.compartment=='fill'],matched_names=sum(r.status not in ('not_found','compartment_mismatch') for r in rows),matched_amounts=sum(r.status=='matched' for r in rows),interpretation='这是单一来源与用户处方的文档比较。即使数值一致，也未证明同一厂家、原研身份、实际商业工艺或一致性评价；不同来源禁止拼接。')

def evaluate(store,root:Path,pid:str,rid:str):
    reference=load_reference(root,pid)
    run=store.run(rid)
    if run['project_id']!=pid: raise HTTPException(404,'运行不属于本项目')
    if run['status'] in ('queued','running'): raise HTTPException(409,'研究仍在运行')
    evidence=store.rows('evidence',pid)
    valid={e['id'] for e in evidence if e['access'] in ('page_text','full_text','imported') and e['basis']=='source'}
    formulas=[RetrievedFormula.model_validate(f) for f in (run.get('report') or {}).get('formulations',[])]
    # Actual model-context file establishes whether answer material was withheld.
    context=root/'workspace/runs'/rid/'input/model-context.json'
    blind=False
    if context.exists():
        data=json.loads(context.read_text(encoding='utf-8'))
        serial=json.dumps(data,ensure_ascii=False)
        # User document/correction and its distinctive quantitative composition must not occur.
        blind=(data.get('project',{}).get('id')==pid and isinstance(data.get('request'),str)
               and isinstance(data.get('evidence'),list) and isinstance(data.get('history'),list)
               and all(marker not in serial for marker in ('126.88','19.20','19.2','user-formulation.png','reference.v1-transcription','user_corrections')))
    limitations=['品牌/厂家未确认，比较不能证明检索到同一个实际产品。','没有逐杯溶出或实验数据，不能进行药学/临床一致判定。']
    if not formulas:limitations.append('本轮没有结构化处方；不得从文字报告猜测成分数量或用量命中率。')
    if not blind:limitations.append('未取得无基准泄漏的模型上下文证据；不能称作盲检成绩。')
    result=CalibrationEvaluation(id=str(uuid4()),run_id=rid,reference_version=reference.version,created_at=now(),blind_context=blind,formulas=[compare_formula(reference,f,valid) for f in formulas],limitations=limitations,comparator_version='1.1')
    path=root/'data/calibrations'/pid;path.mkdir(parents=True,exist_ok=True)
    fingerprint=hashlib.sha256(reference.model_dump_json().encode()).hexdigest()
    target=path/f'{rid}-v{reference.version}-compare1.1.json'
    if target.exists():return CalibrationEvaluation.model_validate_json(target.read_text(encoding='utf-8'))
    # Atomic replace, immutable report per run/reference version.
    temp=target.with_suffix('.tmp');temp.write_text(result.model_dump_json(indent=2),encoding='utf-8');temp.replace(target)
    store.event(rid,'calibration_compared',{'reference_version':reference.version,'reference_fingerprint':fingerprint,'blind_context':blind,'formula_count':len(formulas)})
    return result

def get_view(store,root,pid):
    reference=load_reference(root,pid)
    folder=root/'data/calibrations'/pid
    evaluations=[CalibrationEvaluation.model_validate_json(p.read_text(encoding='utf-8')) for p in sorted(folder.glob('*.json'))] if folder.is_dir() else []
    plan=root/'reference/flunarizine-calibration/process-plan.json'
    benchmark=plan.with_name('process-benchmark.json')
    return {'reference':reference,'evaluations':evaluations,'process_plan':json.loads(plan.read_text(encoding='utf-8')) if plan.exists() else {},'process_benchmark':json.loads(benchmark.read_text(encoding='utf-8')) if benchmark.exists() else {}}
