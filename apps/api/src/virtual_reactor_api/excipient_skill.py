"""Project-scoped bridge to the local excipient research skill."""
import hashlib
import importlib.util
import json
import threading
import uuid
from urllib.parse import urlsplit
from pathlib import Path
from .capsule_models import EvidenceInput

_render_lock=threading.Lock()

def resolve_evidence_references(case, byid):
    """Resolve project-local evidence links without inventing external sources."""
    for side in ('source','target'):
        for ref in case.get(side,{}).get('references',[]):
            url=ref.get('url','')
            if not url.startswith('evidence:'):continue
            eid=url.removeprefix('evidence:')
            evidence=byid.get(eid)
            if not evidence:raise ValueError('引用证据不属于当前项目：'+eid)
            source_url=evidence.get('source_url','')
            if urlsplit(source_url).scheme not in ('http','https'):raise ValueError('该证据无公开原文地址，请引用其原始来源证据：'+eid)
            ref.update(url=source_url,evidence_id=eid)
SKILL_FILES=('SKILL.md','references/portable-workflow.md','references/paired-workflow.md','references/cross-drug-research.md','references/filler-mechanism.md','../excipient-grade-evidence/SKILL.md','../excipient-mechanism-model/SKILL.md','../excipient-model-validation/SKILL.md','../excipient-mechanism-model/assets/powder-yield-example.json')

def powder_yield(root, data):
    """Load only the reviewed fixed calculator, never model-supplied code or paths."""
    path=Path(root)/'.agents/skills/excipient-mechanism-model/scripts/powder_yield.py'
    spec=importlib.util.spec_from_file_location('registered_powder_yield',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.solve(data)

def save_stage(store,pid,run_id,material,stage,record,source_ids):
    if stage not in ('evidence','model','validation'):raise ValueError('stage must be evidence, model or validation')
    if not isinstance(material,str) or not material.strip():raise ValueError('具体物料/规格变化名称不能为空')
    if not isinstance(record,dict) or not isinstance(record.get('summary'),str) or not record['summary'].strip():raise ValueError('阶段记录须有summary')
    if record.get('status') not in ('in_progress','blocked','ready_for_review'):raise ValueError('必须明确阶段状态，不能自动标记科学验证完成')
    if not isinstance(record.get('next_actions'),list) or not all(isinstance(x,str) for x in record['next_actions']):raise ValueError('next_actions须为具体下一步列表')
    if store.run(run_id)['project_id']!=pid:raise ValueError('运行不属于当前项目')
    ids={e['id'] for e in store.rows('evidence',pid)}
    if any(s not in ids for s in source_ids):raise ValueError('引用证据不属于当前项目')
    raw=json.dumps(record,ensure_ascii=False,allow_nan=False)
    if len(raw.encode())>200000:raise ValueError('阶段记录过大，请按专项拆分')
    digest=hashlib.sha256(json.dumps([run_id,material,stage,record,source_ids],ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()
    old=next((e for e in store.rows('evidence',pid) if e.get('fields',{}).get('excipient_stage_hash')==digest),None)
    if old:return old
    return store.add_evidence(pid,EvidenceInput(section='comparison',title=f'辅料专项阶段 · {material} · {stage}',basis='hypothesis',access='imported',
        text=record['summary'],applicability='阶段研究记录，未自动采纳为处方、参数或实测；ready_for_review仅代表可供复核。',
        fields={'excipient_stage_json':raw,'excipient_stage':stage,'excipient_material':material,'excipient_stage_hash':digest,'source_ids_json':json.dumps(source_ids)}),run_id)

def rate_transfer(before,after,baseline,source_delta_fraction,target_delta_fraction,transfer_strength=1):
    """Registered reduced-model calculator, never executes model-supplied code."""
    import numpy as np
    from scipy.optimize import least_squares
    from scipy.interpolate import PchipInterpolator
    arrays=[]
    for points in (before,after,baseline):
        arr=np.asarray(points,dtype=float)
        if arr.ndim!=2 or arr.shape[1]!=2 or not 3<=len(arr)<=500 or not np.isfinite(arr).all():raise ValueError('每条曲线需3–500个有限数值点')
        if np.any(np.diff(arr[:,0])<=0) or np.any(arr<0) or np.any(arr[:,1]>100):raise ValueError('本计算器仅接受递增非负时间及0–100%数据；不裁剪原始超界值')
        arrays.append(arr)
    b,a,base=arrays
    if b.shape!=a.shape or not np.array_equal(b[:,0],a[:,0]):raise ValueError('来源对照需相同采样时间')
    if base[0,0]!=0 or base[0,1]!=0 or np.any(np.diff(base[:,1])<0):raise ValueError('目标基线需明确的(0,0)及单调数据；不得自动改写实测')
    if not np.isfinite([source_delta_fraction,target_delta_fraction,transfer_strength]).all() or source_delta_fraction==0 or abs(source_delta_fraction)>1 or abs(target_delta_fraction)>1 or not 0<=transfer_strength<=1:raise ValueError('比例增量/迁移强度无效')
    t=b[:,0];y=np.array([b[:,1],a[:,1]])
    def predict(times,p):return p[0]*(-np.expm1(-np.exp(p[1:])[:,None]*times))
    fit=least_squares(lambda p:(predict(t,p)-y).ravel(),[80,np.log(.1),np.log(.05)],bounds=([0,-12,-12],[100,3,3]))
    if not fit.success:raise ValueError('数值拟合未收敛')
    p=fit.x;beta=(p[2]-p[1])/source_delta_fraction
    factor=float(np.exp(transfer_strength*beta*target_delta_fraction))
    if not np.isfinite(factor) or factor<=0:raise ValueError('时间缩放不可计算')
    grid=np.linspace(0,base[-1,0]/max(1,factor),241)
    curve=PchipInterpolator(base[:,0],base[:,1],extrapolate=False)
    residual=predict(t,p)-y
    return {'model_id':'effective-rate-transfer-v1','Qcap':float(p[0]),'k_before':float(np.exp(p[1])),'k_after':float(np.exp(p[2])),
        'beta':float(beta),'time_scale':factor,'rmse_pp':np.sqrt(np.mean(residual**2,axis=1)).tolist(),
        'max_error_pp':float(np.max(abs(residual))),'source_before_fit':np.c_[t,predict(t,p)[0]].tolist(),
        'source_after_fit':np.c_[t,predict(t,p)[1]].tolist(),'target_baseline':np.c_[grid,curve(grid)].tolist(),
        'target_prediction':np.c_[grid,curve(factor*grid)].tolist(),
        'assumptions':['Q=Qcap(1-exp(-kt))，来源两组联合校准，不是独立验证。','log(k)对明确组成坐标局部线性；目标只有统一时间尺度改变。','粒度、润湿、分散及润滑作用未独立定参；需要实验确认。'],
        'warning':'仅用于已明确采用综合有效速率迁移假设的情景，不能替代其它辅料的机制模型。'}

def skill_bundle(root:Path):
    folder=root/'.agents/skills/excipient-performance'
    parts=[(name,(folder/name).read_text(encoding='utf-8')) for name in SKILL_FILES]
    content='\n\n'.join(f'[{name}]\n{text}' for name,text in parts)
    return content,hashlib.sha256(content.encode()).hexdigest()

def renderer(root):
    path=root/'.agents/skills/excipient-performance/scripts/paired_case_report.py'
    spec=importlib.util.spec_from_file_location('project_excipient_report',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def publish_case(store,root,pid,case,source_ids=(),run_id=None):
    snapshot=store.snapshot(pid).model_dump()
    if not isinstance(case,dict):raise ValueError('报告应为JSON对象')
    # Bind to the invoking project; model/user input cannot select another one.
    case=json.loads(json.dumps(case,ensure_ascii=False,allow_nan=False))
    case['project_context']={'project':snapshot['project'],'state':'冻结研究情景，不自动关联当前调整方案',
        'comparison_evidence_ids':[e['id'] for e in snapshot['evidence'] if 'comparison' in ' '.join(e.get('fields',{}))]}
    byid={e['id']:e for e in snapshot['evidence']}
    resolve_evidence_references(case,byid)
    if any(s not in byid for s in source_ids):raise ValueError('引用证据不属于当前项目')
    if any(byid[s]['basis'] not in ('source','image_estimate','measurement') or byid[s]['access']=='snippet' for s in source_ids):raise ValueError('引用须为已取得的来源/图像估读/实测证据，不能只引用搜索线索或模型假设')
    raw=json.dumps(case,ensure_ascii=False,sort_keys=True,allow_nan=False)
    if len(raw)>2_000_000:raise ValueError('报告过大，请精简曲线采样')
    module=renderer(root)
    module.validate(case)
    digest=hashlib.sha256(raw.encode()).hexdigest()
    existing=next((e for e in snapshot['evidence'] if e.get('fields',{}).get('excipient_case_hash')==digest),None)
    if existing:return existing
    artifact=uuid.uuid4().hex
    folder=root/'data/excipient-reports'/pid/artifact
    with _render_lock:module.render(case,folder)
    _,skill_hash=skill_bundle(root)
    result=store.add_evidence(pid,EvidenceInput(section='comparison',title=case['title'],
        text='辅料替换双栏研究：'+case['source']['changes']+'\n目标：'+case['target']['changes']+'\n需要实验确认；结构校验和拟合误差不证明来源或迁移科学有效。',
        basis='hypothesis',access='imported',applicability='冻结研究情景，非当前处方自动预测。后续处方/工艺变化需重新核对。',
        fields={'excipient_case_json':raw,'excipient_case_hash':digest,'excipient_artifact':artifact,
                'excipient_skill_hash':skill_hash,'source_ids_json':json.dumps(list(source_ids))}),run_id)
    return result

def artifact_path(store,root,pid,eid,name):
    allowed={'report.html','comparison.svg','comparison.png','case.json','audit.json'}
    if name not in allowed:raise ValueError('未知报告文件')
    store.project(pid)
    row=next((e for e in store.rows('evidence',pid) if e['id']==eid),None)
    artifact=(row or {}).get('fields',{}).get('excipient_artifact','')
    if len(artifact)!=32 or any(c not in '0123456789abcdef' for c in artifact):raise ValueError('报告不存在')
    path=root/'data/excipient-reports'/pid/artifact/name
    if not path.is_file():raise ValueError('报告文件不存在')
    return path
