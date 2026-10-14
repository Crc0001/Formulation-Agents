from .interaction_agent import INTERACTION_MARKER, INTERACTION_POLICY, audit_interactions, share_sources, ResearchTarget, validate_target, continuation_context, research_increment
"""Two isolated research agents, versioned handoff, catalog and anchor API."""
import asyncio,json,math,hashlib,sqlite3,os,re
from pathlib import Path
from contextlib import asynccontextmanager
from uuid import uuid4
from typing import Literal
from fastapi import FastAPI,HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field,model_validator
from .research_reuse import reuse_bundle
from .agent_split import DoeInput,inventory,design,ORGANIZE_MARKER,ORGANIZE_POLICY,audit_organization,organization_review
from .capsule_models import Model,ProjectInput
from .capsule_store import Store,now
from .capsule_research import research
from .mcc_pgs import source_relations, register_sources, target_coordinates
ROOT=Path(__file__).resolve().parents[4]

class Ingredient(Model):
    id:str
    name:str=Field(min_length=1)
    role:Literal['api','excipient','shell']
    amount_mg:float=Field(gt=0)
    brand:str=''
    grade:str=''
    particle:str=''
class BaselineInput(Model):
    title:str=Field(min_length=1)
    ingredients:list[Ingredient]=Field(min_length=2)
    process:str=Field(min_length=1)
    api_particle:str=Field(min_length=1)
    mass_basis:str=Field(min_length=1)
    source_ids:list[str]=Field(min_length=1)
    rationale:str=Field(min_length=1)
    screening_scope:Literal['whole_unit','core_or_fill']='whole_unit'
    fixed_outer_context:str=''
    @model_validator(mode='after')
    def unique(self):
        if self.screening_scope=='core_or_fill' and (not self.fixed_outer_context or any(x.role=='shell' for x in self.ingredients)):raise ValueError('片芯/内容物筛选须保留固定包衣/壳说明，且不得将其列入可计算物料')
        if self.screening_scope=='whole_unit' and self.fixed_outer_context:raise ValueError('有外层固定上下文时须明确片芯/内容物范围')
        if len({x.id for x in self.ingredients})!=len(self.ingredients):raise ValueError('物料ID重复')
        if sum(x.role=='api' for x in self.ingredients)!=1:raise ValueError('必须有且仅有一个API')
        return self
class VariantInput(Model):
    baseline_id:str
    title:str=Field(min_length=1)
    ingredients:list[Ingredient]
    method:str=Field(min_length=1)
    total_policy:Literal['fixed','variable']='fixed'
class HypothesisFreeze(Model):
    run_id:str
    variant_id:str
    prediction:str=Field(min_length=10)
    falsifier:str=Field(min_length=10)

class TopicRequest(Model):
    materials:list[str]=Field(min_length=2,max_length=2)
    model_profile:str|None=None

class ModelApplication(Model):
    source_run_id:str
    evidence_id:str
    variant_id:str
    values:list[float]

class RunRequest(Model):
    include_coating:bool=False
    continue_from_run_id: str | None = None
    research_target: ResearchTarget | None = None
    research_phase:Literal["hypothesis","validation"]="hypothesis"
    hypothesis_id:str|None=None
    baseline_id:str|None=None
    model_profile:str|None=None
    question:str=Field(min_length=1)
    variant_id:str|None=None
class DissolutionInput(Model):
    baseline_id:str
    source_id:str
    sample:str=Field(min_length=1)
    locator:str=Field(min_length=1)
    binding_note:str=Field(min_length=10)
    medium:str=Field(min_length=1)
    volume_ml:float=Field(gt=0)
    rpm:float=Field(gt=0)
    apparatus:str=Field(min_length=1)
    temperature:str='原文未明确'
    points:list[list[float]]=Field(min_length=2,max_length=100)
    @model_validator(mode='after')
    def check(self):
        if any(len(p)!=2 or not all(math.isfinite(x) for x in p) or p[0]<0 for p in self.points):raise ValueError('时间与溶出值须有限；时间非负')
        if any(b[0]<=a[0] for a,b in zip(self.points,self.points[1:])):raise ValueError('时间须严格递增')
        return self
class PairStudyInput(Model):
    variant_id:str
class StageFitInput(Model):
    profile_id:str
class SimulationInput(Model):
    variant_id:str
    tau_min:float=Field(gt=0)
    beta:float=Field(gt=0,le=10)
    source:str=Field(min_length=3)
    basis:Literal['source_parameter','explicit_hypothesis']
class AnchorInput(Model):
    variant_id:str
    prediction_id:str|None=None
    batch:str=Field(min_length=1)
    method:str=Field(min_length=1)
    points:list[list[float]]=Field(min_length=1)
    @model_validator(mode='after')
    def valid_points(self):
        if any(len(p)!=2 or not all(math.isfinite(v) for v in p) or p[0]<0 for p in self.points):raise ValueError('每点须为非负时间和有限实测值；超界实测保留，不裁剪')
        return self
class CatalogInput(Model):
    name:str=Field(min_length=1)
    manufacturer:str=''
    grade:str=''
    market:str=''
    specification:str=Field(min_length=1)
    source_url:str=Field(min_length=1)
    locator:str=Field(min_length=1)
    limitations:str=Field(min_length=1)
    @model_validator(mode='after')
    def url(self):
        if not self.source_url.startswith(('https://','http://')):raise ValueError('来源须为HTTP(S)地址')
        return self

def check_brand_inputs(items):
    for x in items:
        name=x['name'] if isinstance(x,dict) else x.name
        brand=x.get('brand','') if isinstance(x,dict) else x.brand
        if re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)\s*(?:mg|g|毫克|克)?',brand.strip(),re.I):
            raise HTTPException(422,f'{name}的品牌/厂家填了“{brand}”，疑似用量。请将用量填入mg/单位栏；真实数字品牌请填写完整厂家名称。未启动研究。')

def check_variant(base,variant):
    check_brand_inputs(variant.ingredients)
    b={x['id']:x for x in base['ingredients']};v={x.id:x.model_dump() for x in variant.ingredients}
    if len(v)!=len(variant.ingredients) or set(b)!=set(v):raise HTTPException(422,'不可新增或删除辅料种类')
    for key,old in b.items():
        new=v[key]
        if (old['name'],old['role'])!=(new['name'],new['role']):raise HTTPException(422,'不可更换物料种类')
        if old['role']!='excipient' and old!=new:raise HTTPException(422,'API及壳的身份、剂量与规格固定')
    if variant.total_policy=='fixed' and abs(sum(x['amount_mg'] for x in b.values())-sum(x['amount_mg'] for x in v.values()))>1e-6:raise HTTPException(422,'总量不一致；请明确补差或选择允许总量变化')

def release(t,tau,beta):
    if t<=0:return 0.0
    log_power=beta*(math.log(t)-math.log(tau))
    if log_power>7:return 100.0
    return 100*(-math.expm1(-math.exp(log_power)))
def curve(tau,beta):
    return [[t,release(t,tau,beta)] for t in range(0,121,2)]
def fit(points):
    xs=[math.log(p[0]) for p in points];ys=[math.log(-math.log1p(-p[1]/100)) for p in points]
    xm=sum(xs)/len(xs);ym=sum(ys)/len(ys);den=sum((x-xm)**2 for x in xs)
    beta=sum((x-xm)*(y-ym) for x,y in zip(xs,ys))/den
    if not 0<beta<=10:raise HTTPException(422,'这些实测不支持当前单调Weibull模型')
    try:tau=math.exp(-(ym-beta*xm)/beta)
    except OverflowError:raise HTTPException(422,'拟合参数超出数值范围')
    if not math.isfinite(tau) or tau<=0:raise HTTPException(422,'拟合参数无效')
    return tau,beta

def create_app(root=ROOT,runner=research):
    root=Path(root);(root/'data').mkdir(parents=True,exist_ok=True)
    stores={k:Store(root/'data'/f'{k}.sqlite3') for k in ['origin','organize','interaction','excipient']}
    for existing in stores['origin'].projects():
        for kind in ('organize','interaction'):
            with stores[kind].db() as c:c.execute('INSERT OR IGNORE INTO projects VALUES(?,?)',(existing['id'],json.dumps(existing,ensure_ascii=False)))
        for kind in ('excipient','interaction'):share_sources(stores[kind],stores['organize'],existing['id'])
    dbpath=root/'data/workbench.sqlite3';active={}
    def db():
        con=sqlite3.connect(dbpath);con.execute('CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,kind TEXT,pid TEXT,payload TEXT)');return con
    def save(kind,pid,data):
        item={'id':str(uuid4()),'created_at':now(),**data}
        with db() as c:c.execute('INSERT INTO records VALUES(?,?,?,?)',(item['id'],kind,pid,json.dumps(item,ensure_ascii=False)))
        return item
    def rows(kind,pid=None):
        with db() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT payload FROM records WHERE kind=?'+(' AND pid=?' if pid else '')+' ORDER BY rowid',(kind,pid) if pid else (kind,))]
    def get(kind,pid,id):
        found=next((r for r in rows(kind,pid) if r['id']==id),None)
        if not found:raise HTTPException(404,'记录不存在或不属于本项目')
        return found
    def save_anchor(pid,data):
        # Anchor and return receipt are committed together; neither can be lost alone.
        from .experiment_feedback import feedback
        item={'id':str(uuid4()),'created_at':now(),**data}
        receipt={'id':str(uuid4()),'created_at':now(),**feedback(item)}
        with db() as c:
            for kind,value in [('anchors',item),('experiment_feedback',receipt)]:
                c.execute('INSERT INTO records VALUES(?,?,?,?)',(value['id'],kind,pid,json.dumps(value,ensure_ascii=False)))
        return item
    def archive_evidence(agent,pid,e):
        from .topic_data_package import digest
        raw=e.get('basis')=='source' and e.get('access') in ('full_text','page_text','imported')
        if raw:
            with stores['organize'].db() as c:
                c.execute('INSERT OR IGNORE INTO evidence VALUES(?,?,?)',(e['id'],pid,json.dumps(e,ensure_ascii=False)))
                existing=json.loads(c.execute('SELECT payload FROM evidence WHERE id=?',(e['id'],)).fetchone()[0])
            if digest(existing)!=digest(e):raise ValueError('原文同ID内容冲突，未覆盖02原文')
        key=digest(e)
        if any(x['evidence_id']==e['id'] and x['content_hash']==key for x in rows('research_archive_receipts',pid)):return
        save('research_archive_receipts',pid,{'evidence_id':e['id'],'content_hash':key,'run_id':e.get('run_id'),
            'agent':agent,'title':e['title'],'basis':e.get('basis'),'access':e.get('access'),
            'destination':'02原始资料' if raw else '02研究成果索引（原件保留研究智能体）',
            'status':'archived' if raw else 'indexed'})
    for kind in ('interaction','excipient'):
        stores[kind].evidence_sink=lambda pid,e,kind=kind:archive_evidence(kind,pid,e)
    from .origin_registry import OriginRegistry
    registry=OriginRegistry(root)
    origin_jobs={}
    @asynccontextmanager
    async def lifespan(app):
        for s in stores.values():s.recover()
        update_task=asyncio.create_task(registry.check())
        batch_task=asyncio.create_task(batch_queue.loop())
        yield
        batch_task.cancel()
        await asyncio.gather(batch_task,return_exceptions=True)
        update_task.cancel()
        for job in origin_jobs.values():job.cancel()
        await asyncio.gather(update_task,*origin_jobs.values(),return_exceptions=True)
        for t in active.values():t.cancel()
        await asyncio.gather(*active.values(),return_exceptions=True)
    app=FastAPI(title='药品研发四智能体',version='3.0.0',lifespan=lifespan)
    @app.get('/api/health')
    def health():
        return {'status':'ok','application':'药品研发双智能体','instance':hashlib.sha256(str(root).encode()).hexdigest()[:12],'configured':(root/'config/agent.local.toml').exists()}
    @app.get('/api/origin-registry')
    def origin_registry():return registry.status()
    @app.get('/api/origin-registry/batches')
    def origin_registry_batches():
        from .directory_backfill import summary
        return summary(registry)
    @app.get('/api/origin-registry/rows')
    def origin_registry_rows(q:str=''):
        from .directory_backfill import search_rows
        return {'rows':search_rows(registry,q[:100]),'note':'历史原表记录；变更尚未完整核对，不代表当前有效资格。'}
    @app.get('/api/projects/{pid}/origin-local-data')
    def origin_local_data(pid:str):
        stores['origin'].project(pid)
        evidence=stores['origin'].rows('evidence',pid)
        return {'sources':[{'id':e['id'],'title':e['title'],'url':e.get('source_url',''),'local_directory':bool(e.get('fields',{}).get('local_directory_key'))} for e in evidence if e.get('basis')=='source']}
    @app.post('/api/origin-registry/check')
    async def origin_registry_check():return await registry.check()
    @app.get('/api/projects')
    def projects():return stores['origin'].projects()
    @app.get('/api/local-case/mecobalamin/source')
    def local_case_source():
        from .retrospective import load_case
        try:source=load_case(root)['source']
        except FileNotFoundError:raise HTTPException(404,'本地原文未导入')
        path=Path(source['file'])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:raise HTTPException(409,'原文文件已缺失或发生变更')
        return FileResponse(path,media_type='application/pdf')
    @app.post('/api/projects')
    def project(v:ProjectInput):
        p=stores['origin'].create_project(v);stores['excipient'].create_project(v,p['id']);stores['organize'].create_project(v,p['id']);stores['interaction'].create_project(v,p['id']);return p
    @app.post('/api/projects/{pid}/source-doe-handoffs')
    def source_doe_handoff(pid:str,body:dict):
        from .source_doe_handoff import prepare
        source=get('image_source_models',pid,body.get('source_model_id'))
        try:public,private=prepare(source)
        except (ValueError,KeyError,TypeError) as ex:raise HTTPException(422,str(ex))
        prior=next((x for x in rows('source_doe_handoffs',pid) if x['handoff_hash']==public['handoff_hash']),None)
        if prior:return prior
        # One transaction: never expose a handoff without its sealed validation record.
        item={'id':str(uuid4()),'created_at':now(),**public}
        sealed={'id':str(uuid4()),'created_at':now(),'handoff_id':item['id'],**private}
        with db() as c:
            for kind,value in [('source_doe_handoffs',item),('source_doe_validation',sealed)]:
                c.execute('INSERT INTO records VALUES(?,?,?,?)',(value['id'],kind,pid,json.dumps(value,ensure_ascii=False)))
        return item
    @app.get('/api/projects/{pid}/source-doe-handoffs/{hid}/training')
    def source_doe_training(pid:str,hid:str):
        return get('source_doe_handoffs',pid,hid)
    @app.post('/api/projects/{pid}/source-pair-contrasts')
    def source_pair_contrasts(pid:str,body:dict):
        from .source_pair_contrasts import save_contrasts
        store=stores['interaction']
        source=next((e for e in store.rows('evidence',pid) if e['id']==body.get('metric_id')),None)
        if not source:raise HTTPException(404,'来源数值记录不存在')
        try:
            e,result=save_contrasts(store,pid,source.get('run_id'),body)
            return {'evidence_id':e['id'],'result':result}
        except (ValueError,TypeError,KeyError) as ex:raise HTTPException(422,str(ex))
    @app.post('/api/projects/{pid}/image-source-models')
    def image_source_model(pid:str,body:dict):
        from .image_source_models import build
        baseline_id=body.get('baseline_id')
        if not any(x['id']==baseline_id for x in rows('research_cases',pid)):get('baselines',pid,baseline_id)
        allowed={x['run_id'] for x in rows('interaction_runs',pid) if x['baseline_id']==baseline_id}
        evidence=[e for e in stores['interaction'].rows('evidence',pid) if e.get('run_id') in allowed]
        try:result=build(evidence,body.get('evidence_ids',[]),root)
        except (ValueError,KeyError,TypeError) as ex:raise HTTPException(422,str(ex))
        existing=next((x for x in rows('image_source_models',pid) if x['baseline_id']==baseline_id and x['result']['input_hash']==result['input_hash'] and x['result']['version']==result['version']),None)
        return existing or save('image_source_models',pid,{'baseline_id':baseline_id,'result':result})
    @app.get('/api/projects/{pid}/interaction/images/{eid}')
    def source_chart_image(pid:str,eid:str):
        import re
        from PIL import Image
        e=next((e for e in stores['interaction'].rows('evidence',pid) if e['id']==eid),None)
        sha=(e or {}).get('fields',{}).get('sha256','')
        if not e or e.get('basis')!='image_estimate' or not re.fullmatch('[a-f0-9]{64}',sha):raise HTTPException(404,'没有归档图片')
        path=root/'data/documents'/sha
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise HTTPException(404,'图片缺失或校验失败')
        try:
            with Image.open(path) as im:fmt=im.format
        except Exception:raise HTTPException(404,'不是图片')
        if fmt not in ('PNG','JPEG'):raise HTTPException(415,'图片格式不支持')
        return FileResponse(path,media_type='image/png' if fmt=='PNG' else 'image/jpeg',headers={'X-Content-Type-Options':'nosniff'})
    @app.get('/api/projects/{pid}')
    def snapshot(pid:str):
        from .patent_completeness import audit_patents
        from .capsule_models import ResearchReport
        from .origin_stages import origin_stage, scope_report
        snapshots={agent:s.snapshot(pid).model_dump() for agent,s in stores.items()}
        for item in snapshots['origin']['runs']:
            if item.get('report'):item['report']=scope_report(item['report'],origin_stage(item.get('message','')))
        # Read-only cumulative view also restores earlier-round observations in old tasks.
        from .origin_delivery import merge_report
        for run in snapshots['interaction']['runs']:
            prior=None
            for record in sorted((x for x in rows('interaction_rounds',pid) if x['run_id']==run['id']),key=lambda x:x['round']):
                if record.get('report'):prior=merge_report(prior,record['report']).model_dump()
            if prior and run.get('report'):
                run['report']=merge_report(prior,run['report']).model_dump()
        # Read-only re-audit makes older omissions visible without rewriting historical reports.
        for value in snapshots.values():
            for run in value['runs']:
                if run.get('report') and origin_stage(run.get('message',''))!=1:
                    run['report']['patent_audit']=audit_patents(ResearchReport.model_validate(run['report']),value['evidence'])
        from .focused_screening import audit_progress
        for value in snapshots.values():
            for item in value['runs']:
                item['screening_audit']=audit_progress((item.get('report') or {}).get('screening_progress'),value['evidence'])
        from .model_research import audit_design
        for value in (snapshots['excipient'],):
            for item in value['runs']:
                if item.get('report',{}):item['model_design_audit']=audit_design(item['report'].get('research_design'),value['evidence'])
        bindings={x['run_id']:x for x in rows('organization_runs',pid)}
        for item in snapshots['organize']['runs']:
            if item['id'] in bindings:
                item['organization_review']=organization_review(item,get('baselines',pid,bindings[item['id']]['baseline_id']),snapshots['organize']['evidence'],stores['organize'].events(item['id']),bindings[item['id']].get('include_coating',False))
        from .lab_formulations import context as case_context
        datasets=rows('lab_formulation_datasets',pid)
        cases=[{**x,'context':case_context(x,next((d for d in datasets if d['id']==x.get('dataset_id')),None))} for x in rows('research_cases',pid)]
        return {'research_cases':cases,'lab_formulation_datasets':[{k:v for k,v in d.items() if k!='trials'}|{'trial_count':len(d['trials']),'materials':sorted({m['name'] for t in d['trials'] for m in t['materials'] if m['role']=='excipient'})} for d in datasets],'project':stores['origin'].project(pid),'research_reuse':{v['id']:reuse_bundle(v,rows('variants',pid),rows('pair_studies',pid),rows('final_calibrations',pid)) for v in rows('variants',pid)},'mcc_pgs_relations':source_relations(root),**snapshots,**{k:rows(k,pid) for k in ['baselines','variants','simulations','anchors','dissolution_profiles','release_models','research_workflows','retrospective_checks','pair_studies','final_calibrations','model_runs','organization_runs','interaction_runs','interaction_progress','interaction_rounds','image_source_models','source_doe_handoffs','doe_plans','hypothesis_versions','experiment_feedback','feedback_uses','doe_model_applications']}}
    @app.post('/api/projects/{pid}/lab-formulation-datasets')
    def import_lab_dataset(pid:str,body:dict):
        from .lab_formulations import LabDataset
        from .topic_data_package import digest
        from .capsule_models import EvidenceInput
        stores['origin'].project(pid)
        try:value=LabDataset.model_validate(body).model_dump()
        except ValueError as ex:raise HTTPException(422,str(ex))
        fingerprint=digest(value)
        existing=next((x for x in rows('lab_formulation_datasets',pid) if x['content_hash']==fingerprint),None)
        if existing:return existing
        from .excipient_properties import library
        known={m['id'] for m in library(root)['materials']}
        links={m['property_record_id'] for t in value['trials'] for m in t['materials'] if m['property_record_id']}
        if not links<=known:raise HTTPException(422,'辅料检测档案ID不存在，不能建立虚假关联')
        evidence=stores['organize'].add_evidence(pid,EvidenceInput(section='comparison',title=value['title'],basis='measurement',access='imported',text=json.dumps(value,ensure_ascii=False),locator='用户导入制剂实验数据包；按trial_id/batch_id定位',applicability='用户提供实验，质量声明不代替数据核对。既有结果属回顾性资料；用途标注不构成已完成独立验证。',fields={'lab_formulation_dataset_hash':fingerprint}))
        return save('lab_formulation_datasets',pid,{**value,'content_hash':fingerprint,'evidence_id':evidence['id'],'status':'imported_not_validated'})
    @app.get('/api/projects/{pid}/lab-formulation-datasets/{dataset_id}')
    def lab_dataset(pid:str,dataset_id:str):return get('lab_formulation_datasets',pid,dataset_id)
    @app.post('/api/projects/{pid}/research-cases')
    def create_research_case(pid:str,body:dict):
        from .lab_formulations import ResearchCase,context
        stores['origin'].project(pid)
        try:value=ResearchCase.model_validate(body).model_dump()
        except ValueError as ex:raise HTTPException(422,str(ex))
        dataset=get('lab_formulation_datasets',pid,value['dataset_id']) if value['dataset_id'] else None
        if dataset:
            names={m['name'] for t in dataset['trials'] for m in t['materials'] if m['role']=='excipient'}
            if not set(value['materials'])<=names:raise HTTPException(422,'研究辅料必须存在于所选实验数据包')
        item=save('research_cases',pid,value)
        return {**item,'context':context(item,dataset)}
    @app.get('/api/projects/{pid}/topic-data')
    def topic_data(pid:str):
        from .topic_data_package import citation_ids
        stores['origin'].project(pid)
        packets=[]
        for p in rows('topic_data_packages',pid):
            run=stores['interaction'].run(p['run_id'])
            cited=citation_ids(run.get('report') or {})
            packets.append({k:v for k,v in p.items() if k not in ('items','baseline_snapshot')}|{
                'materials':p['baseline_snapshot']['ingredients'],
                'items':[{'evidence_id':i['evidence_id'],'content_hash':i['content_hash'],'title':i['snapshot']['title'],
                    'basis':i['snapshot']['basis'],'access':i['snapshot']['access'],'cited':i['evidence_id'] in cited} for i in p['items']],
                'report_cited_ids':sorted(cited)})
        return {'packages':packets,'receipts':rows('research_archive_receipts',pid),'legacy_run_ids':[x['run_id'] for x in rows('interaction_runs',pid) if not x.get('data_package_id')]}
    @app.get('/api/projects/{pid}/topic-data/{package_id}')
    def topic_data_snapshot(pid:str,package_id:str):
        return get('topic_data_packages',pid,package_id)
    @app.get('/api/projects/{pid}/data-sources')
    def data_sources(pid:str):
        stores['origin'].project(pid)
        labels={r['evidence_id']:r for r in rows('data_source_labels',pid)}
        collected={}
        for agent,store in stores.items():
            for e in store.rows('evidence',pid):
                if e.get('basis') not in ('source','measurement'):continue
                if e['id'] in collected:
                    collected[e['id']]['agents'].append(agent)
                    continue
                url=e.get('source_url','')
                category='unclassified'
                if '/api/local-case/' in url or e.get('fields',{}).get('lab_formulation_dataset_hash'):category='formulation_lab'
                elif e.get('fields',{}).get('verified_workbook_sha256'):category='lab'
                elif url.startswith(('http://','https://')):category='literature_pending'
                label=labels.get(e['id'])
                collected[e['id']]={**e,'category':label['category'] if label else category,'classification_basis':'用户归类' if label else '已知本地实验资料' if category in ('lab','formulation_lab') else '网络来源，类型待核对' if category=='literature_pending' else '待归类','agents':[agent]}
        return {'sources':list(collected.values())}
    @app.post('/api/projects/{pid}/data-sources/{eid}/category')
    def label_data_source(pid:str,eid:str,body:dict):
        category=body.get('category')
        if category not in ('lab','formulation_lab','third_party','literature','unclassified'):raise HTTPException(422,'资料类型无效')
        if not any(e['id']==eid and e.get('basis') in ('source','measurement') for store in stores.values() for e in store.rows('evidence',pid)):
            raise HTTPException(404,'项目原始资料不存在')
        return save('data_source_labels',pid,{'evidence_id':eid,'category':category})
    @app.get('/api/excipient-properties')
    def excipient_properties():
        from .excipient_properties import library
        return library(root)
    @app.get('/api/excipient-properties/source/{source_id}')
    def excipient_properties_source(source_id:str):
        from .excipient_properties import library
        entry=next((x for x in library(root)['imports'] if x['id']==source_id),None)
        if not entry:raise HTTPException(404,'来源不存在')
        path=root/entry['archive']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=source_id:raise HTTPException(409,'原始归档校验失败')
        return FileResponse(path,filename=entry['filename'])
    @app.get('/api/model-profiles')
    def model_profiles():
        from .model_profiles import public_profiles
        return public_profiles(root)
    @app.post('/api/projects/{pid}/final-calibrations')
    def final_calibration(pid:str,v:PairStudyInput):
        from .final_calibration import execute
        project=stores['origin'].project(pid)
        if project['api']!='甲钴胺' or project['dosage_form']!='片剂':raise HTTPException(422,'该实际资料仅适用于甲钴胺片剂')
        variant=get('variants',pid,v.variant_id);base=get('baselines',pid,variant['baseline_id'])
        try:result=execute(root,base,variant)
        except (ValueError,FileNotFoundError) as ex:raise HTTPException(422,str(ex))
        return save('final_calibrations',pid,result)
    @app.post('/api/projects/{pid}/pair-studies')
    def pair_study(pid:str,v:PairStudyInput):
        from .native_starch_pair import execute
        variant=get('variants',pid,v.variant_id)
        base=get('baselines',pid,variant['baseline_id'])
        try:result=execute(root,base,variant,rows('dissolution_profiles',pid))
        except (ValueError,FileNotFoundError) as ex:raise HTTPException(422,str(ex))
        return save('pair_studies',pid,result)
    @app.post('/api/projects/{pid}/retrospective-checks')
    def retrospective_check(pid:str):
        from .retrospective import execute,load_case
        project=stores['origin'].project(pid)
        if project['api']!='甲钴胺' or project['dosage_form']!='片剂':raise HTTPException(422,'本来源适配器仅用于甲钴胺片剂验证项目')
        if not (root/'reference/mecobalamin-validation-20260925/dataset.json').is_file():raise HTTPException(404,'尚未导入核验数据')
        return save('retrospective_checks',pid,execute(load_case(root)))
    @app.post('/api/projects/{pid}/dissolution-profiles')
    def dissolution_profile(pid:str,v:DissolutionInput):
        base=get('baselines',pid,v.baseline_id)
        source=next((e for e in stores['origin'].rows('evidence',pid) if e['id']==v.source_id),None)
        if not source or source['basis']!='source' or source['access'] not in ('full_text','page_text','imported'):raise HTTPException(422,'需要本项目已读取的原始来源')
        # Binding is an explicit review record; original frozen baseline is immutable.
        value=v.model_dump()
        for previous in rows('dissolution_profiles',pid):
            if all(previous.get(k)==x for k,x in value.items()):return previous
        with stores['excipient'].db() as c:c.execute('INSERT OR IGNORE INTO evidence VALUES(?,?,?)',(source['id'],pid,json.dumps(source,ensure_ascii=False)))
        return save('dissolution_profiles',pid,{**value,'baseline_snapshot':base,'source_url':source.get('source_url'),'basis':'published_source','status':'人工核对绑定的来源样品曲线，非目标批次实测'})
    @app.post('/api/projects/{pid}/release-models')
    def release_model(pid:str,v:StageFitInput):
        from .release_stages import fit_profile
        profile=get('dissolution_profiles',pid,v.profile_id)
        try:value=fit_profile(profile)
        except ValueError as ex:raise HTTPException(422,str(ex))
        return save('release_models',pid,value)
    @app.post('/api/projects/{pid}/baselines')
    def baseline(pid:str,v:BaselineInput):
        stores['origin'].project(pid);sources={e['id']:e for e in stores['origin'].rows('evidence',pid)}
        from .baseline_sources import baseline_sources
        try:resolved,warnings=baseline_sources(v.source_ids,sources)
        except ValueError as ex:raise HTTPException(422,str(ex))
        data=v.model_dump();data['source_ids']=resolved
        data['evidence_warnings']=warnings
        if warnings:data['mass_basis']+='\n'+'\n'.join(warnings)
        data['version']=len(rows('baselines',pid))+1;data['signature']=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
        for id in resolved:
            with stores['excipient'].db() as c:c.execute('INSERT OR IGNORE INTO evidence VALUES(?,?,?)',(id,pid,json.dumps(sources[id],ensure_ascii=False)))
        return save('baselines',pid,data)
    @app.post('/api/projects/{pid}/variants')
    def variant(pid:str,v:VariantInput):
        base=get('baselines',pid,v.baseline_id);check_variant(base,v);return save('variants',pid,{**v.model_dump(),'process':base['process'],'api_particle':base['api_particle'],'mass_basis':base['mass_basis'],'screening_scope':base.get('screening_scope','whole_unit'),'fixed_outer_context':base.get('fixed_outer_context','')})
    @app.get('/api/projects/{pid}/inventory/{baseline_id}')
    def full_inventory(pid:str,baseline_id:str,include_coating:bool=False):return inventory(get('baselines',pid,baseline_id),include_coating)
    @app.post('/api/projects/{pid}/hypotheses')
    def freeze_hypothesis(pid:str,v:HypothesisFreeze):
        variant=get('variants',pid,v.variant_id)
        source=stores['excipient'].run(v.run_id)
        if source['project_id']!=pid or ('"id": "'+variant['id']+'"') not in source['message']:raise HTTPException(422,'报告与当前方案不匹配')
        design=(source.get('report') or {}).get('research_design')
        if not design or not design.get('hypotheses'):raise HTTPException(422,'先形成包含假设、方程与适用条件的研究报告')
        return save('hypothesis_versions',pid,{'run_id':v.run_id,'variant_id':v.variant_id,'variant_snapshot':variant,'design':design,'prediction':v.prediction,'falsifier':v.falsifier,'status':'待验证假设；冻结不代表模型成立','prior_exposure':'既有实验结果已被查阅，后续属回顾性验证，不是事前盲预测'})
    def model_packages(pid,baseline_id):
        from .doe_model_package import package
        return [package(b,stores['interaction'].run(b['run_id']),stores['interaction'].rows('evidence',pid))
                for b in rows('interaction_runs',pid) if b['baseline_id']==baseline_id
                and stores['interaction'].run(b['run_id']).get('report')]
    def topic_library():
        from .doe_model_package import package
        from .lab_formulations import context
        from .calculation_handoff import variant_identity
        library=[]
        for project in stores['origin'].projects():
            pid=project['id'];bases={b['id']:b for b in rows('baselines',pid)}
            bases.update({c['id']:context(c) for c in rows('research_cases',pid)})
            evidence=stores['interaction'].rows('evidence',pid)
            for binding in rows('interaction_runs',pid):
                target=binding.get('research_target') or {}
                if target.get('kind')!='pair':continue
                base=bases.get(binding['baseline_id'])
                if not base:continue
                names=[m['name'] for m in base['ingredients'] if m['id'] in target.get('material_ids',[])]
                if len(names)!=2:continue
                research=stores['interaction'].run(binding['run_id'])
                p=package(binding,research,evidence)
                p.update(project_id=pid,project_name=project['name'],materials=sorted(names),status=research['status'],created_at=research['created_at'])
                # Preserve explicit ownership of old 04 curve calculations. Link only when
                # the same baseline and exact original source already belong to this topic.
                sources={m['record'].get('source_id') for m in p['models']} - {None}
                from .topic_data_package import citation_ids
                sources |= citation_ids((research.get('report') or {}).get('interaction_research') or {})
                for e in stores['excipient'].rows('evidence',pid):
                    raw=e.get('fields',{}).get('source_curve_model_json')
                    if not raw or not e.get('run_id'):continue
                    try:
                        record=json.loads(raw);identity=variant_identity(stores['excipient'].run(e['run_id']))
                    except (ValueError,KeyError,TypeError):continue
                    curve_sources={a.get('source_id') for a in record.get('arms',[])} - {None}
                    if identity and identity[1]==binding['baseline_id'] and curve_sources and curve_sources<=sources:
                        p['models'].append({'evidence_id':e['id'],'kind':'source_curve_model_json','title':e['title'],'record':record,'origin_agent':'04','source_url':e.get('source_url')})
                p['studies']=((research.get('report') or {}).get('interaction_research') or {}).get('studies',[])
                library.append(p)
        published={};latest={}
        for p in library:
            key=(p['project_id'],p['baseline_id'],tuple(p['materials']))
            latest[key]=p
            if p['models']:published[key]=p
        result=[]
        for key,p in latest.items():
            if key in published:result.append(published[key])
            if key not in published or (p['status'] in ('queued','running') and p['run_id']!=published[key]['run_id']):result.append(p)
        return result
    @app.get('/api/projects/{pid}/reference-design')
    def reference_design(pid:str, reference_id:str|None=None):
        from .reference_design import analyze
        if not __import__('re').fullmatch(r'[a-zA-Z0-9-]+',pid):raise HTTPException(404,'项目不存在')
        path=root/'data'/'reference-designs'/(pid+'.json')
        if not path.exists():return {'available':False}
        data=json.loads(path.read_text(encoding='utf8'))
        if reference_id is None:return {'available':True,'references':data['references'],'comparability':data['comparability']}
        try:return analyze(data,reference_id)
        except ValueError as e:raise HTTPException(422,str(e))
    @app.get('/api/research-topics')
    def research_topics():return topic_library()
    @app.post('/api/projects/{pid}/topic-research')
    async def topic_research(pid:str,v:TopicRequest):
        stores['origin'].project(pid)
        names=sorted(x.strip() for x in v.materials)
        if not all(names) or len(set(names))!=2:raise HTTPException(422,'请选择或填写两个不同辅料')
        candidates=[p for p in topic_library() if p['project_id']==pid and p['materials']==names]
        running=next((p for p in reversed(candidates) if p['status'] in ('queued','running')),None)
        if running:return {'run_id':running['run_id'],'status':running['status'],'reused':True}
        previous=next((p for p in reversed(candidates) if p['status'] not in ('queued','running')),None)
        if previous:
            baseline_id=previous['baseline_id'];target=previous['research_target']
        else:
            case=create_research_case(pid,{'title':'—'.join(names)+' · 典型制剂专题','mode':'literature','materials':names,'objective':'研究两种辅料配比对片剂全程释放的影响机制与关系模型','dosage_form':'片剂'})
            baseline_id=case['id'];target={'kind':'pair','material_ids':['case-material-1','case-material-2'],'objective':case['objective']}
        r=await run(pid,'interaction',RunRequest(baseline_id=baseline_id,research_target=ResearchTarget.model_validate(target),model_profile=v.model_profile,continue_from_run_id=previous['run_id'] if previous else None,
            question='由04工作台请求03科研：围绕本辅料配对，优先交付全程释放原始对照曲线、影响机制及有数据支持的配比响应模型。已有计算直接复用；补齐具体缺口，硬度等作为辅助响应。来源制剂条件、品牌规格和机制边界明确，成果用于04观察及试验设计，不直接移植为当前药物预测。'))
        return {'run_id':r['id'],'status':r['status'],'reused':False}
    @app.get('/api/projects/{pid}/doe-model-packages')
    def available_models(pid:str,baseline_id:str):
        stores['origin'].project(pid)
        get('baselines',pid,baseline_id)
        return model_packages(pid,baseline_id)
    @app.post('/api/projects/{pid}/doe-model-applications')
    def apply_source_model(pid:str,v:ModelApplication):
        from .doe_model_package import evaluate
        from .topic_data_package import digest
        variant=get('variants',pid,v.variant_id)
        p=next((p for p in model_packages(pid,variant['baseline_id']) if p['run_id']==v.source_run_id),None)
        if not p:raise HTTPException(422,'03模型必须属于同项目和冻结基准')
        m=next((m for m in p['models'] if m['evidence_id']==v.evidence_id and m['kind']=='source_response_model_json'),None)
        if not m:raise HTTPException(422,'该03版本未引用此连续响应模型')
        try:result=evaluate(m,v.values)
        except (ValueError,KeyError,TypeError) as ex:raise HTTPException(422,str(ex)) from None
        value={'source_run_id':v.source_run_id,'source_package_version':p['version'],'evidence_id':v.evidence_id,
               'variant_id':variant['id'],'baseline_id':variant['baseline_id'],'variant_snapshot':variant,
               'model_snapshot':m,'result':result,'input_levels':v.values}
        key=digest(value)
        old=next((x for x in rows('doe_model_applications',pid) if x['content_hash']==key),None)
        return old or save('doe_model_applications',pid,{**value,'content_hash':key})
    @app.post('/api/projects/{pid}/doe-plans')
    def doe_plan(pid:str,v:DoeInput):
        base=get('baselines',pid,v.baseline_id)
        try:value=design(base,v)
        except ValueError as ex:raise HTTPException(422,str(ex))
        return save('doe_plans',pid,value)
    @app.post('/api/projects/{pid}/{agent}/runs')
    async def run(pid:str,agent:Literal['origin','organize','interaction','excipient'],v:RunRequest):
        s=stores[agent];s.project(pid)
        from .model_profiles import resolve,using_profile
        try: selected_model=resolve(root,v.model_profile or 'glm') if v.model_profile or (root/'config/glm.local.toml').exists() else None
        except ValueError as ex:raise HTTPException(422,str(ex)) from None
        if agent=='origin':
            from .origin_local import preload
            local_packet=preload(registry,s,pid)
            await registry.check()
        if agent=='organize':
            if not v.baseline_id:raise HTTPException(422,'先选择01交付的冻结基准，不需要调整方案')
            base=get('baselines',pid,v.baseline_id)
            for kind in ('origin','interaction','excipient'):share_sources(stores[kind],s,pid)
            from .excipient_properties import research_context
            from .agent_split import organization_scope
            message='【处方辅料筛选】'+ORGANIZE_MARKER+'\n'+ORGANIZE_POLICY+'\n冻结基准：'+json.dumps(base,ensure_ascii=False)+'\n全方目录：'+json.dumps(inventory(base,v.include_coating),ensure_ascii=False)+'\n问题：'+v.question+research_context(root,base['ingredients'],s,pid)+'\n'+organization_scope(v.include_coating)
        elif agent=='interaction':
            if not v.research_target:raise HTTPException(422,'请先填写03本次研究目标：辅料配对或单辅料规格变化')
            if not v.baseline_id:raise HTTPException(422,'先选择01冻结基准，无需修改处方')
            case=next((x for x in rows('research_cases',pid) if x['id']==v.baseline_id),None)
            dataset=None
            if case:
                from .lab_formulations import context as case_context
                dataset=get('lab_formulation_datasets',pid,case['dataset_id']) if case.get('dataset_id') else None
                base=case_context(case,dataset)
            else:base=get('baselines',pid,v.baseline_id)
            try:target=validate_target(v.research_target,base)
            except ValueError as ex:raise HTTPException(422,str(ex)) from None
            for kind in ('origin','excipient','interaction'):share_sources(stores[kind],stores['organize'],pid)
            share_sources(stores['organize'],s,pid)
            packets=[{'run_id':x['run_id'],'report':stores['organize'].run(x['run_id']).get('report')} for x in rows('organization_runs',pid) if x['baseline_id']==base['id']]
            history=[{'run_id':x['run_id'],'report':s.run(x['run_id']).get('report')} for x in rows('interaction_runs',pid) if x['baseline_id']==base['id'] and x.get('research_target')==target]
            message=INTERACTION_MARKER+'\n本次冻结研究目标：'+json.dumps(target,ensure_ascii=False)+'\n'+INTERACTION_POLICY+'\n冻结基准：'+json.dumps(base,ensure_ascii=False)+'\n配对目录：'+json.dumps(inventory(base),ensure_ascii=False)+'\n02研究包：'+json.dumps(packets[-3:],ensure_ascii=False)+'\n同基准历史配对研究（保留条件，逐步补缺）：'+json.dumps(history,ensure_ascii=False)+'\n本轮问题：'+v.question
            from .excipient_properties import research_context
            message+=research_context(root,base['ingredients'],s,pid)
            if v.continue_from_run_id:
                binding=next((x for x in rows('interaction_runs',pid) if x['run_id']==v.continue_from_run_id),None)
                if not binding or binding['baseline_id']!=base['id'] or binding.get('research_target')!=target:
                    raise HTTPException(422,'继续研究必须使用原任务相同的基准和目标')
                previous=s.run(v.continue_from_run_id)
                if previous['status'] in ('queued','running'):raise HTTPException(409,'原任务仍在运行')
                message+='\n'+json.dumps(continuation_context(previous),ensure_ascii=False)
            if case:
                message+='\n【独立研究对象，优先于所在项目药物】'+json.dumps(base,ensure_ascii=False)+'。这是研究目录，不是01冻结的定量处方，不推算缺失用量。文献模式先选数据充分的来源制剂。'
            if dataset:
                e=next(e for e in stores['organize'].rows('evidence',pid) if e['id']==dataset['evidence_id'])
                with s.db() as c:c.execute('INSERT OR IGNORE INTO evidence VALUES(?,?,?)',(e['id'],pid,json.dumps(e,ensure_ascii=False)))
                message+='\n【实验室实际制剂数据包】'+json.dumps(dataset,ensure_ascii=False)+'。既有实验结果已暴露，属于回顾性研究；按batch_id分组避免训练验证泄漏。先核对单位、工艺、补差和混杂；未实现的拟合工具说明待实现，不用语言心算冒充程序求解。'
            feedback_items=[x for x in rows('experiment_feedback',pid) if x['baseline_id']==base['id']]
            if feedback_items:
                message+='\n【04实测回传03：模型修订输入】'+json.dumps(feedback_items,ensure_ascii=False)+'。逐项核对方案、批次和检测方法，先比较冻结预测与实测偏差，再评估适用域和参数修订。保留原模型及预测；拟合曲线不是实测。已读取结果的后续拟合不得声称独立验证。研究对象不匹配的记录明确排除，不能混合不同方案拟合。输出引用回传ID和anchor_id的复核结论，新模型另存计算证据；缺工具时明确未完成校准。'
            evidence_before=s.rows('evidence',pid)
        elif agent=='excipient':
            if not v.variant_id:raise HTTPException(422,'请先冻结基准并保存辅料方案')
            variant=get('variants',pid,v.variant_id);base=get('baselines',pid,variant['baseline_id'])
            check_brand_inputs(variant['ingredients'])
            message='【处方辅料筛选】你是辅料筛选智能体，物料种类和API固定。\n冻结基准：'+json.dumps(base,ensure_ascii=False)+'\n变化方案：'+json.dumps(variant,ensure_ascii=False)+'\n问题：'+v.question+'\n必须交付规格/品牌数据库catalog_findings及本轮substitution_assessment；有依据时使用现有局部物性工具并保存图形计算，不猜整方参数。'
            from .excipient_properties import research_context
            message+=research_context(root,base['ingredients']+variant['ingredients'],s,pid)
            package_runs=[x for x in rows('organization_runs',pid) if x['baseline_id']==base['id']]
            packet=next((stores['organize'].run(x['run_id']) for x in reversed(package_runs) if stores['organize'].run(x['run_id']).get('report')),None)
            if packet:
                for e in stores['organize'].rows('evidence',pid):
                    with s.db() as c:c.execute('INSERT OR IGNORE INTO evidence VALUES(?,?,?)',(e['id'],pid,json.dumps(e,ensure_ascii=False)))
                message+='\n02已交付研究包（仅同一基准候选，非参数采纳）：'+json.dumps({'run_id':packet['id'],'status':packet['status'],'report':packet['report'],'current_review':organization_review(packet,base,s.rows('evidence',pid),stores['organize'].events(packet['id']),next((x.get('include_coating',False) for x in package_runs if x['run_id']==packet['id']),False))},ensure_ascii=False)
            from .doe_model_package import compact
            packages=model_packages(pid,base['id'])
            # Most recent model-bearing version per exact topic; old versions stay archived.
            latest={}
            for p in packages:
                if p['models']:latest[json.dumps(p['research_target'],sort_keys=True,ensure_ascii=False)]=p
            changed={m['id'] for m in variant['ingredients'] if any(b['id']==m['id'] and any(b.get(k)!=m.get(k) for k in ('amount_mg','brand','grade','particle')) for b in base['ingredients'])}
            selected_packages=[p for p in latest.values() if changed.intersection((p.get('research_target') or {}).get('material_ids',[]))]
            for e in stores['interaction'].rows('evidence',pid):
                with s.db() as c:c.execute('INSERT OR IGNORE INTO evidence VALUES(?,?,?)',(e['id'],pid,json.dumps(e,ensure_ascii=False)))
            message+='\n【03可计算模型交付04】'+json.dumps([compact(p) for p in selected_packages],ensure_ascii=False)
            applications=[x for x in rows('doe_model_applications',pid) if x['variant_id']==variant['id']]
            message+='\n【04已执行来源模型应用】'+json.dumps(applications[-3:],ensure_ascii=False)
            message+='\n04职责：直接利用03交付模型及保存的计算结果，说明本次变化、优先假设、来源依据、适用域和目标迁移缺口，交付screening_progress.judgment。不要重复全面文献研究或重拟合已有模型。来源关系支持条件假设，不自动成为当前药物定量预测；模型不足时具体列出需03补齐的组成映射、适用条件或参数，并给出可检验的主假设和反证。03补科研模型，04应用模型与设计校准。'
            bundle=reuse_bundle(variant,rows('variants',pid),rows('pair_studies',pid),rows('final_calibrations',pid))
            if v.research_phase=='validation':message+='\n相同保存条件的历史研究（保留来源版本；不得忽略已有同药趋势，也不得把最终处方校准当作当前配比验证）：'+json.dumps(bundle,ensure_ascii=False)
            pair_records=bundle['pair_studies'] if v.research_phase=='validation' else []
            if pair_records:message+='\n本方案独立乳糖—原生玉米淀粉复验（仅来源作者参数，非目标预测）：'+json.dumps(pair_records[-1],ensure_ascii=False)+'\n优先处理该模块next_actions，不重做无关示例。source_curves是作者参数重建，不是原始实测；target_curves为空表示迁移未通过。'
            profiles=[x for x in rows('dissolution_profiles',pid) if x['baseline_id']==base['id']]
            message+='\n已核对绑定的来源溶出基线：'+json.dumps(profiles,ensure_ascii=False)+'\n优先读取03已经保存的来源复现和误差，核对其与当前处方的适用关系。不得忽略已有溶出基线或将其冒充目标实验。'
        else:
            from .origin_stages import origin_message, origin_stage
            message=origin_message(v.question,s.project(pid))
            from .origin_stages import identity_sources
            message+='\n【先读自建库，再定缺口】'+json.dumps(local_packet,ensure_ascii=False)
            message+='\n本项目已存原文摘录（完整原文按证据ID读取）：'+json.dumps(identity_sources(s.rows('evidence',pid)),ensure_ascii=False)
            from .directory_backfill import search_rows
            directory_state=registry.status()
            message+='\n共享参比目录查新状态：'+json.dumps(directory_state['latest'],ensure_ascii=False)
            message+='\n本品历史目录原表记录（尚未完成后续变更核验；按来源回查，不能直接当现行资格或原研身份）：'+json.dumps(search_rows(registry,stores['origin'].project(pid).get('api',''))[:30],ensure_ascii=False)
        contract=root/'reference/model-led-contract.md'
        if agent=='excipient' and contract.exists():message+='\n'+contract.read_text(encoding='utf-8-sig')
        if agent=='excipient':
            origin_packages=[{'run_id':x['id'],'research_design':x['report']['research_design']} for x in stores['origin'].rows('runs',pid) if x.get('report',{} ) and x['report'].get('research_design')]
            message+='\n原研模型包（历史候选，必须核对与冻结基准身份匹配后使用）：'+json.dumps(origin_packages[-3:],ensure_ascii=False)
        known_models=[{'id':m['id'],'baseline_id':m['baseline_id'],'profile_id':m['profile_id'],'model_id':m['model_id'],'best':m['best'],'status':m['status'],'residuals_pp':m['residuals_pp'],'assumptions':m['assumptions']} for m in rows('release_models',pid)]
        if agent not in ('origin','interaction'):message+='\n已有独立保存的三阶段数值复算（不是辅料贡献实测）：'+json.dumps(known_models,ensure_ascii=False)
        case_path=root/'reference/cross-formulation-validation-20260924/results.json'
        local_checks=rows('retrospective_checks',pid)
        if local_checks and agent=='excipient' and v.research_phase=='validation':
            from .retrospective import register_calculation
            calc_id=register_calculation(s,pid,local_checks[-1])
            message+='\n本项目独立案例复验：'+json.dumps(local_checks[-1],ensure_ascii=False)+'\n以上计算的可引用证据ID：'+calc_id+'。record id是运行记录而非证据编号；source_ids和calculation_evidence_id必须使用可引用证据ID。网页已实现整方留出曲线和逐点残差，不要把当前语言模型无绘图工具说成程序没有图。仅解读本案例，不能用其它药或预胶化淀粉替代玉米淀粉。该记录不自动预测当前方案。'
        if agent=='excipient':
            if v.research_phase=='validation':
                if not v.hypothesis_id:raise HTTPException(422,'验证前先冻结假设、预期结果和推翻条件')
                frozen=get('hypothesis_versions',pid,v.hypothesis_id)
                if frozen['variant_id']!=variant['id']:raise HTTPException(422,'冻结假设不属于所选方案')
                message+='\n【验证阶段】先逐项比较以下冻结预测与实验，再提出修订；不得回写原假设。'+json.dumps(frozen,ensure_ascii=False)
            else:
                message+='\n【假设建立阶段】先依据文献及辅料功能数据提出竞争假设，以界面作用、润湿、孔结构、解聚、传质解释，再给出方程、单位、参数来源、适用域、可检验预测与推翻条件。缺参数可保留符号或有来源的范围，不伪造数值。净方向unknown不阻止提出可检验假设：评估整体加快、整体减慢及早晚相对差值变号分支，说明主假设排序依据，证据不足则保留竞争而非停止。每个适用分支交付组成到中间物性到模型参数的具体映射、方向条件和推翻条件；不强行保留不适用分支。不得用任意参数滑块、预设方向曲线或要求用户选参数代替研究。03已交付来源模型时直接引用模型及误差，不重复拟合。尚缺组成映射或模型参数时列为返回03的定向研究任务。累计溶出不因相对差值变号而下降。优先来源对照复验，不能仅以建议目标实验作为全部交付。使用research_design展示。既有目标实验及其拟合不能充当前述机制推导；如查阅过须披露，不称盲预测。本阶段不自动重跑目标实验校准，实验用于后续验证。'
        continuation=None
        if agent=='excipient':
            from .research_limits import is_summary_recovery
            if v.continue_from_run_id or is_summary_recovery(message):
                from .calculation_handoff import continuation_package
                try:continuation=continuation_package(s.rows('runs',pid),s.rows('evidence',pid),pid,variant,v.continue_from_run_id)
                except ValueError as ex:raise HTTPException(422,str(ex)) from None
                message+='\n04接续研究交接包：'+json.dumps(continuation,ensure_ascii=False)
        r=s.create_run(pid,message)
        if continuation:
            s.event(r['id'],'calculation_handoff',{'previous_run_id':continuation['previous_run_id'],'calculation_ids':continuation['calculation_ids'],'missing_calculation_ids':continuation['missing_calculation_ids']})
        if agent=='interaction':
            if feedback_items:
                save('feedback_uses',pid,{'run_id':r['id'],'baseline_id':base['id'],'feedback_ids':[x['id'] for x in feedback_items],'status':'delivered','meaning':'已纳入03研究输入，不等于复核通过或模型修订完成'})
            from .topic_data_package import freeze
            previous=next((x for x in reversed(rows('topic_data_packages',pid)) if x['run_id']==v.continue_from_run_id),None) if v.continue_from_run_id else None
            package=save('topic_data_packages',pid,{'run_id':r['id'],**freeze(base,target,evidence_before,previous)})
            save('interaction_runs',pid,{'run_id':r['id'],'baseline_id':base['id'],'research_target':target,'continue_from_run_id':v.continue_from_run_id,'inventory':inventory(base),'data_package_id':package['id']})
            s.event(r['id'],'topic_data_frozen',{'package_id':package['id'],'count':len(package['items']),'added':len(package['added_ids']),'changed':len(package['changed_ids'])})
        if agent=='organize':save('organization_runs',pid,{'run_id':r['id'],'baseline_id':base['id'],'include_coating':v.include_coating,'inventory':inventory(base,v.include_coating)})
        if selected_model:
            save('model_runs',pid,{'run_id':r['id'],'agent':agent,'profile_id':selected_model['profile_id'],'label':selected_model['label'],'model':selected_model['model']})
            s.event(r['id'],'model_selected',{'model':selected_model['model'],'label':selected_model['label']})
        async def work():
            try:
                workflow=None
                if agent=='excipient' and v.research_phase=='validation' and local_checks:
                    from .retrospective import execute,load_case,register_calculation
                    s.finish(r['id'],'running')
                    check=save('retrospective_checks',pid,{'run_id':r['id'],**await asyncio.to_thread(execute,load_case(root))})
                    s.event(r['id'],'workflow_executed',{'workflow_id':check['id'],'steps':[],'target_prediction_available':False})
                    calc_id=register_calculation(s,pid,check,r['id'])
                    s.finish(r['id'],'running',message=s.run(r['id'])['message']+'\n本轮后台重新执行记录：'+json.dumps(check,ensure_ascii=False)+'\n本轮可引用计算证据ID：'+calc_id+'。禁止把check.id当成source_ids。该证据含F1–F9逐点预测及观察，网页直接绘图。')
                if agent=='excipient' and v.research_phase=='validation' and not local_checks:
                    from .research_workflow import execute_workflow,register_case_source
                    s.finish(r['id'],'running')
                    save('research_workflows',pid,{'run_id':r['id'],'variant_id':variant['id'],'baseline_id':base['id'],'status':'running','steps':[]})
                    source_id=None # Unrelated method demonstrations are not target evidence.
                    pair_source_ids=register_sources(s,pid,r['id'],root) if target_coordinates(base,variant) else []
                    value=await asyncio.to_thread(execute_workflow,root,base,variant,profiles)
                    value['case_source_id']=source_id
                    value['mcc_pgs_source_ids']=pair_source_ids
                    workflow=save('research_workflows',pid,{'run_id':r['id'],**value})
                    s.event(r['id'],'workflow_executed',{'workflow_id':workflow['id'],'steps':workflow['steps'],'target_prediction_available':False})
                    from .capsule_models import EvidenceInput
                    execution=s.add_evidence(pid,EvidenceInput(section='comparison',title='本轮程序计算记录 '+workflow['id'],text=json.dumps(workflow,ensure_ascii=False),basis='hypothesis',access='imported',locator='research_workflows/'+workflow['id'],applicability='后端实际执行的模型计算；不是来源实测或已验证目标预测。',fields={'workflow_id':workflow['id']}),run_id=r['id'])
                    current_message=s.run(r['id'])['message']
                    current_message+='\n来源原文证据ID：'+str(source_id)+'；本轮计算证据ID：'+execution['id']+'。引用原文用来源ID；计算推断用hypothesis身份及计算ID，workflow_id不是source_id。\n本轮程序实际执行的四步验收：'+json.dumps(workflow,ensure_ascii=False)+'\n报告优先交付冻结方案实际变化对应的物料配对关系、来源原表、复算误差与目标域判断。仅当变化确为MCC—预胶化淀粉时使用其条件模型；其它药物案例必须说明与本次变化的物料及机理对应，不默认套用。不得以无关资料分类替代本轮目标。已有来源基线不再列为未取得；目标变化关系仍未知，明确具体下一步。'
                    s.finish(r['id'],'running',message=current_message)
                with using_profile(selected_model):
                    if agent=='interaction' and '【接续：汇总】' not in v.question:
                        from .interaction_rounds import run_topic
                        await run_topic(s,r['id'],root,runner,lambda value:save('interaction_rounds',pid,value),base['id'],{'materials':[x for x in base['ingredients'] if x['id'] in target['material_ids']],'dosage_context':base.get('title','')})
                    else:await runner(s,r['id'],root)
                report=s.run(r['id']).get('report') or {}
                if agent=='excipient' and workflow and report and s.run(r['id'])['status'] not in ('cancelled','failed','interrupted'):
                    from .research_workflow import gate_report
                    report=gate_report(report,workflow)
                    s.finish(r['id'],'partial',report=report)
                if agent=='excipient' and report:
                    from .focused_screening import audit_progress
                    check=audit_progress(report.get('screening_progress'),s.rows('evidence',pid))
                    if check['issues']:
                        report['gaps']=list(dict.fromkeys([*report.get('gaps',[]),*check['issues']]))
                        s.finish(r['id'],'partial',report=report)
                if agent=='origin' and report and origin_stage(message) not in (1,2):
                    rec=report.get('origin_recommendation')
                    if not rec or rec.get('formula_title') not in [f['title'] for f in report.get('formulations',[])]:
                        report['gaps']=[*report.get('gaps',[]),'未交付可对应候选处方的推荐基准；不能完成基准交接']
                        s.finish(r['id'],'partial',report=report)
                if agent=='interaction' and report:
                    save('interaction_progress',pid,{'run_id':r['id'],'baseline_id':base['id'],'research_target':target,**research_increment(evidence_before,s.rows('evidence',pid),r['id'])})
                    issues=audit_interactions(report.get('interaction_research'),base,s.rows('evidence',pid),target)
                    if issues:
                        report['gaps']=list(dict.fromkeys([*report.get('gaps',[]),*issues]))
                        status=s.run(r['id'])['status']
                        s.finish(r['id'],status if status in ('failed','cancelled','interrupted') else 'partial',report=report)
                if agent=='organize' and report:
                    issues=audit_organization(report.get('excipient_organization'),base,s.rows('evidence',pid),v.include_coating)
                    if issues:
                        report['gaps']=list(dict.fromkeys([*report.get('gaps',[]),*issues]))
                        status=s.run(r['id'])['status']
                        s.finish(r['id'],status if status in ('failed','cancelled','interrupted') else 'partial',report=report)
                if agent=='excipient' and report and not report.get('research_design') and s.run(r['id'])['status'] not in ('cancelled','failed','interrupted'):
                    report['gaps']=list(dict.fromkeys([*report.get('gaps',[]),'本轮未交付research_design：基准模型、候选判别及锚点设计尚未完成。']))
                    s.finish(r['id'],'partial',report=report)
                evidence={e['id']:e for e in s.rows('evidence',pid)}
                for item in report.get('catalog_findings',[]):
                    refs=[evidence[x] for x in item.get('source_ids',[]) if x in evidence and evidence[x]['basis']=='source' and evidence[x]['access'] in ('full_text','page_text','imported')]
                    if refs:save('catalog_'+agent,pid,{**item,'project_id':pid,'run_id':r['id'],'status':'研究条目，未确认采纳','sources':[{'id':e['id'],'title':e['title'],'url':e['source_url'],'locator':e['locator']} for e in refs]})
            except asyncio.CancelledError:
                if agent=='excipient':save('research_workflows',pid,{'run_id':r['id'],'variant_id':variant['id'],'baseline_id':base['id'],'status':'cancelled','steps':[],'completion_note':'运行已取消；先前完成的计算记录保留。'})
                s.finish(r['id'],'cancelled',error='已取消；已取得证据保留');raise
            except Exception as ex:
                if agent=='excipient':save('research_workflows',pid,{'run_id':r['id'],'variant_id':variant['id'],'baseline_id':base['id'],'status':'failed','steps':[],'completion_note':'流程未执行完成：'+type(ex).__name__})
                s.finish(r['id'],'failed',error=type(ex).__name__)
            finally:
                if agent in ('interaction','excipient'):
                    count=share_sources(s,stores['organize'],pid)
                    for item in s.rows('evidence',pid):
                        if item.get('run_id')==r['id']:
                            try:archive_evidence(agent,pid,item)
                            except Exception as ex:s.event(r['id'],'evidence_archive_pending',{'id':item['id'],'error_type':type(ex).__name__})
                    s.event(r['id'],'sources_shared',{'count':count,'target':'02','reason':'原始来源已归档到02；假设和计算独立保留'})
        task=asyncio.create_task(work());active[r['id']]=task;task.add_done_callback(lambda _:active.pop(r['id'],None));return r
    @app.get('/api/projects/{pid}/origin-autostart')
    def origin_auto_status(pid:str):
        stores['origin'].project(pid)
        return {'running':pid in origin_jobs,'last_error':next(iter(reversed(rows('origin_auto_status',pid))),None)}
    @app.post('/api/projects/{pid}/origin-autostart')
    async def origin_autostart(pid:str,model_profile:str="astra"):
        from .model_profiles import resolve
        try:resolve(root,model_profile)
        except ValueError as ex:raise HTTPException(status_code=400,detail=str(ex))
        stores['origin'].project(pid)
        if pid in origin_jobs:return {'status':'running'}
        if stores['origin'].rows('runs',pid):return {'status':'existing_archive','message':'已有研究，保留成果，不自动重新运行'}
        async def sequence():
            try:
                for phase,question in enumerate(('核对原研身份、中国正式参比目录及各国说明书，区分研发者、持有人、生产厂和参比资格，逐项保存来源与辅料名单。','沿原研及上市时间追溯专利族、审评报告及文献，提取完整定量处方和对应工艺性能，未知量不得补造。','比较已有定量候选，优先原研关联和说明书辅料匹配，推荐可执行的试验参考，不自动冻结。'),1):
                    r=await run(pid,'origin',RunRequest(question=f'【01阶段{phase}】'+question,model_profile=model_profile))
                    task=active.get(r['id'])
                    if task:await task
                    saved=stores['origin'].run(r['id'])
                    if saved['status'] not in ('completed','partial') or not saved.get('report') or saved.get('error'):break
                    if phase==1 and not (saved['report'].get('decision_comparison') or saved['report'].get('formulations')):break
                    if phase==2 and not saved['report'].get('formulations'):break
            except asyncio.CancelledError:raise
            except Exception as ex:save('origin_auto_status',pid,{'status':'failed','reason':type(ex).__name__,'message':'自动建档中断；请检查模型配置或使用定向补查，不自动重复启动。'})
            finally:origin_jobs.pop(pid,None)
        origin_jobs[pid]=asyncio.create_task(sequence())
        return {'status':'started','message':'自动研究已排队；失败或缺关键交付时停止，不重复重试'}
    @app.post('/api/{agent}/runs/{rid}/cancel')
    def cancel(agent:Literal['origin','organize','interaction','excipient'],rid:str):
        r=stores[agent].run(rid)
        if rid in active:active[rid].cancel()
        return r
    @app.get('/api/{agent}/runs/{rid}/events')
    def events(agent:Literal['origin','organize','interaction','excipient'],rid:str):
        stores[agent].run(rid)
        return [{'kind':e['kind'],'created_at':e['created_at'],'detail':e['payload'] if e['kind'] in ('model_selected','agent_started','search_request','document_request','research_followup','run_status','model_error','provider_failure','research_recovery','workflow_executed','origin_extract_progress','origin_extract_saved','origin_extract_error','search_query_corrected','research_checkpoint') else {}} for e in stores[agent].events(rid) if e['kind'] not in ('model_request','model_response','search_provider_response')]
    @app.get('/api/catalog/{agent}')
    def catalog(agent:Literal['origin','organize','interaction','excipient']):return rows('catalog_'+agent)
    @app.post('/api/catalog/{agent}')
    def catalog_add(agent:Literal['origin','organize','interaction','excipient'],v:CatalogInput):return save('catalog_'+agent,'external',{**v.model_dump(),'status':'外部导入待核验','sources':[{'url':v.source_url,'locator':v.locator}]})
    @app.get('/api/integrations/excipient/schema')
    def integration():return {'version':'1','read':'GET /api/catalog/excipient','write':'POST /api/catalog/excipient','schema':CatalogInput.model_json_schema(),'network':'默认仅本机；未配置任何外连账号；导入记录待核，不自动变为模型参数'}
    @app.post('/api/projects/{pid}/simulations')
    def simulate(pid:str,v:SimulationInput):
        variant=get('variants',pid,v.variant_id)
        return save('simulations',pid,{**v.model_dump(),'model':'weibull-local-v1','equation':'Q=100*(1-exp(-(t/tau)^beta))','status':'未校准条件情景；不是品牌到性能的自动预测','variant_snapshot':variant,'points':curve(v.tau_min,v.beta)})
    @app.post('/api/projects/{pid}/experiment-feedback/sync')
    def sync_feedback(pid:str):
        stores['origin'].project(pid)
        from .experiment_feedback import feedback
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            payloads=[(k,json.loads(p)) for k,p in c.execute('SELECT kind,payload FROM records WHERE pid=? AND kind IN (?,?)',(pid,'anchors','experiment_feedback'))]
            known={x['anchor_id'] for k,x in payloads if k=='experiment_feedback'}
            added=0
            for kind,item in payloads:
                if kind!='anchors' or item['id'] in known:continue
                value={'id':str(uuid4()),'created_at':now(),**feedback(item)}
                c.execute('INSERT INTO records VALUES(?,?,?,?)',(value['id'],'experiment_feedback',pid,json.dumps(value,ensure_ascii=False)))
                added+=1
        return {'added':added}
    @app.post('/api/projects/{pid}/anchors')
    def anchor(pid:str,v:AnchorInput):
        variant=get('variants',pid,v.variant_id)
        if v.method!=variant['method']:raise HTTPException(422,'方法与冻结方案不一致，不能作为同体系锚点')
        prediction=get('simulations',pid,v.prediction_id) if v.prediction_id else None
        if prediction and prediction['variant_id']!=v.variant_id:raise HTTPException(422,'预测不属于同一方案，不能混用锚点')
        eligible=[p for p in v.points if p[0]>0]
        if any(x in v.method for x in ('未知','未确定','待定','待补')) or len({p[0] for p in eligible})<3 or any(not 0<p[1]<100 for p in eligible) or any(p[0]==0 and p[1]!=0 for p in v.points):
            return save_anchor(pid,{**v.model_dump(),'variant_snapshot':variant,'model':'weibull-local-v1','tau_min':None,'beta':None,'points_fitted':[],'fit_rmse_pp':None,'prior_rmse_pp':None,'status':'实测原值已保存，当前模型不可拟合：需明确检测方法及至少3个不同正时间且0<Q<100；未裁剪数值','prior':prediction})
        try:tau,beta=fit(eligible)
        except HTTPException:
            return save_anchor(pid,{**v.model_dump(),'variant_snapshot':variant,'model':'weibull-local-v1','tau_min':None,'beta':None,'points_fitted':[],'fit_rmse_pp':None,'prior_rmse_pp':None,'status':'实测已保存，但不支持当前单调模型','prior':prediction})
        calc=release
        rmse=lambda a,b:math.sqrt(sum((q-calc(t,a,b))**2 for t,q in v.points)/len(v.points))
        return save_anchor(pid,{**v.model_dump(),'variant_snapshot':variant,'model':'weibull-local-v1','tau_min':tau,'beta':beta,'calibration_interval_min':[min(p[0] for p in eligible),max(p[0] for p in eligible)],'points_fitted':[[t,release(t,tau,beta)] for t in [max(p[0] for p in eligible)*i/60 for i in range(61)]],'fit_rmse_pp':rmse(tau,beta),'prior_rmse_pp':rmse(prediction['tau_min'],prediction['beta']) if prediction else None,'status':'同方案同方法经验校准，非独立验证；不迁移到其他规格','prior':prediction})
    @app.get('/api/capsule/projects/{pid}/excipient-cases/{eid}/{name}')
    def artifact(pid:str,eid:str,name:str):
        from .excipient_skill import artifact_path
        try:path=artifact_path(stores['excipient'],root,pid,eid,name)
        except ValueError:raise HTTPException(404,'报告不存在')
        return FileResponse(path,headers={'Content-Security-Policy':"default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"})
    from .origin_batch import BatchResearch
    async def submit_batch(pid,question,model):
        return await run(pid,'origin',RunRequest(question=question,model_profile=model))
    batch_queue=BatchResearch(root,registry,stores['origin'],project,submit_batch)
    @app.get('/api/origin-registry/batches/{batch}/research')
    async def batch_status(batch:int):return batch_queue.view(batch)
    @app.post('/api/origin-registry/batches/{batch}/research')
    async def batch_start(batch:int,model_profile:str='astra'):
        from .model_profiles import resolve
        try:
            resolve(root,model_profile)
            return await batch_queue.start(batch,model_profile)
        except ValueError as ex:raise HTTPException(422,str(ex)) from None
    @app.post('/api/origin-registry/batches/{batch}/research/retry')
    async def batch_retry(batch:int,project_id:str,model_profile:str='glm',summary_only:bool=False):
        from .model_profiles import resolve
        try:
            resolve(root,model_profile)
            return await batch_queue.retry(batch,project_id,model_profile,summary_only)
        except ValueError as ex:raise HTTPException(422,str(ex)) from None
    @app.post('/api/origin-registry/batches/{batch}/research/pause')
    async def batch_pause(batch:int):return await batch_queue.pause(batch)
    from .batch_transfer import BatchTransfer,install_routes
    install_routes(app,BatchTransfer(root,stores,batch_queue))
    dist=root/'apps/web/dist'  
    if (dist/'assets').exists():app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
    @app.get('/')
    def index():return FileResponse(dist/'index.html',headers={'Cache-Control':'no-store'})
    return app
app=create_app()
