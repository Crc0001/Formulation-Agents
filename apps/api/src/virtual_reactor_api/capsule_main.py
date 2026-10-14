"""Capsule-only application entry point; no reaction/campaign routes."""
import asyncio
import hashlib
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse,StreamingResponse,Response
from fastapi.staticfiles import StaticFiles
from .capsule_models import ProjectInput,Project,EvidenceInput,Evidence,TaskInput,Task,TaskUpdate,RunInput,Run,Snapshot,Event,CalibrationView,CalibrationEvaluation
from .capsule_store import Store
from .capsule_import import import_case
from .capsule_research import research
from .capsule_coverage import coverage, CoverageView

ROOT=Path(__file__).resolve().parents[4]
logging.getLogger('httpx').setLevel(logging.WARNING)

def create_app(root:Path=ROOT, *, runner=research, seed=True):
    store=Store(root/'data/capsule.sqlite3')
    active={}
    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        if seed: import_case(store,root)
        yield
        for task in active.values(): task.cancel()
        await asyncio.gather(*list(active.values()),return_exceptions=True)
    app=FastAPI(title='Capsule Generics',version='1.1.0',lifespan=lifespan)
    app.state.store=store

    @app.get('/api/capsule/health')
    def health():
        # No provider credentials or internal paths returned.
        try:
            from .agent_runtime import AgentRuntimeSettings
            AgentRuntimeSettings.from_sources(os.environ,config_path=root/'config/agent.local.toml')
            configured=True
        except Exception: configured=False
        return {'status':'ok','application':'Capsule Generics','version':'1.1.0','instance_id':hashlib.sha256(os.path.normcase(str(root.resolve())).encode()).hexdigest()[:16],'research_configured':configured}

    @app.get('/api/capsule/projects',response_model=list[Project])
    def projects(): return store.projects()

    @app.get('/api/capsule/excipient-skill')
    def excipient_skill_status():
        from .excipient_skill import skill_bundle
        try:
            _,digest=skill_bundle(root)
            return {'available':True,'version':digest[:12],'name':'辅料替换验证','mode':'文献对照与目标条件预测'}
        except OSError:
            return {'available':False,'name':'辅料替换验证','error':'技能文件缺失'}

    @app.post('/api/capsule/projects/{pid}/excipient-cases',response_model=Evidence,status_code=201)
    def save_excipient_case(pid:str,value:dict):
        from .excipient_skill import publish_case
        store.project(pid)
        try:
            return publish_case(store,root,pid,value['case'],value.get('source_ids',[]))
        except (ValueError,KeyError,TypeError) as ex:
            raise HTTPException(422,str(ex))

    @app.get('/api/capsule/projects/{pid}/excipient-cases/{eid}/{name}')
    def excipient_case_artifact(pid:str,eid:str,name:str):
        from .excipient_skill import artifact_path
        try:path=artifact_path(store,root,pid,eid,name)
        except ValueError:raise HTTPException(404,'报告文件不存在')
        return FileResponse(path,headers={'Content-Security-Policy':"default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox",'X-Content-Type-Options':'nosniff'})

    @app.post('/api/capsule/projects',response_model=Project,status_code=201)
    def create(value:ProjectInput): return store.create_project(value)

    @app.get('/api/capsule/projects/{pid}',response_model=Snapshot)
    def snapshot(pid:str): return store.snapshot(pid)

    @app.post('/api/capsule/projects/{pid}/evidence',response_model=Evidence,status_code=201)
    def evidence(pid:str,value:EvidenceInput): return store.add_evidence(pid,value)

    @app.post('/api/capsule/projects/{pid}/tasks',response_model=Task,status_code=201)
    def task(pid:str,value:TaskInput): return store.add_task(pid,value)

    @app.put('/api/capsule/projects/{pid}/tasks/{tid}',response_model=Task)
    def update_task(pid:str,tid:str,value:TaskUpdate): return store.update_task(pid,tid,value)

    @app.post('/api/capsule/projects/{pid}/runs',response_model=Run,status_code=202)
    async def start(pid:str,value:RunInput):
        r=store.create_run(pid,value.message)
        async def guarded_run():
            try:
                await runner(store,r['id'],root)
                if store.run(r['id'])['status'] in ('queued','running'):
                    store.finish(r['id'],'failed',error='运行未形成终态，已保存证据保留。')
            except asyncio.CancelledError:
                if store.run(r['id'])['status'] in ('queued','running'):
                    store.finish(r['id'],'cancelled',error='研究已取消，已保存证据保留。')
                raise
            except Exception as ex:
                store.finish(r['id'],'failed',error='研究启动或执行失败：'+type(ex).__name__)
        t=asyncio.create_task(guarded_run())
        active[r['id']]=t
        t.add_done_callback(lambda _:active.pop(r['id'],None))
        return r

    @app.get('/api/capsule/runs/{rid}',response_model=Run)
    def get_run(rid:str): return store.run(rid)

    @app.post('/api/capsule/runs/{rid}/cancel',response_model=Run)
    async def cancel(rid:str):
        r=store.run(rid)
        if r['status'] in ('queued','running'):
            if rid in active:
                active[rid].cancel()
                await asyncio.gather(active[rid],return_exceptions=True)
            if store.run(rid)['status'] in ('queued','running'):
                store.finish(rid,'cancelled',error='用户取消研究，已保存证据保留。')
        return store.run(rid)

    @app.get('/api/capsule/runs/{rid}/events',response_model=list[Event])
    def events(rid:str,after:int=0):
        store.run(rid)
        return store.events(rid,after)

    @app.get('/api/capsule/runs/{rid}/stream')
    async def stream(rid:str,request:Request,after:int=0):
        store.run(rid)
        try: cursor=max(after,int(request.headers.get('last-event-id','0')))
        except ValueError: cursor=after
        async def generate():
            nonlocal cursor
            while not await request.is_disconnected():
                for event in store.events(rid,cursor):
                    cursor=event['id']
                    yield f'id: {cursor}\ndata: {json.dumps(event,ensure_ascii=False)}\n\n'
                if store.run(rid)['status'] not in ('queued','running'): break
                yield ': heartbeat\n\n'
                await asyncio.sleep(1)
        return StreamingResponse(generate(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

    @app.get('/api/capsule/projects/{pid}/coverage',response_model=CoverageView)
    def source_coverage(pid:str): return coverage(store,pid)

    @app.get('/api/capsule/projects/{pid}/export')
    def export(pid:str):
        data=store.snapshot(pid).model_dump()
        data['schema_version']='1.0'
        policy_file=root/'reference/research-policy.json'
        data['research_policy']=json.loads(policy_file.read_text(encoding='utf-8')) if policy_file.exists() else None
        data['coverage']=coverage(store,pid).model_dump()
        data['events']={r['id']:store.events(r['id']) for r in data['runs']}
        if pid=='flunarizine-cn-5-calibration':
            from .capsule_calibration import get_view
            data['calibration']=CalibrationView.model_validate(get_view(store,root,pid)).model_dump()
        return Response(json.dumps(data,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="capsule-project.json"'})

    @app.get('/api/capsule/projects/{pid}/calibration',response_model=CalibrationView)
    def calibration(pid:str):
        from .capsule_calibration import get_view
        store.project(pid)
        return get_view(store,root,pid)

    @app.post('/api/capsule/projects/{pid}/calibration/{rid}',response_model=CalibrationEvaluation)
    def compare(pid:str,rid:str):
        from .capsule_calibration import evaluate
        return evaluate(store,root,pid,rid)

    @app.get('/api/capsule/projects/{pid}/calibration/image')
    def calibration_image(pid:str):
        from .capsule_calibration import reference_path
        store.project(pid)
        path=reference_path(root,pid).with_name('user-formulation.png')
        return FileResponse(path,media_type='image/png')

    @app.get('/api/capsule/projects/{pid}/evidence/{eid}/document')
    def document(pid:str,eid:str):
        store.project(pid)
        row=next((e for e in store.rows('evidence',pid) if e['id']==eid),None)
        digest=(row or {}).get('fields',{}).get('sha256','')
        if not re.fullmatch(r'[a-f0-9]{64}',digest): raise HTTPException(404,'尚未归档原始文件')
        path=root/'data/documents'/digest
        if not path.is_file(): raise HTTPException(404,'归档文件不存在')
        with path.open('rb') as stream: pdf=stream.read(4)==b'%PDF'
        image_mime=(row or {}).get('fields',{}).get('document_mime','')
        if image_mime in ('image/png','image/jpeg'):
            return FileResponse(path,media_type=image_mime,headers={'X-Content-Type-Options':'nosniff'})
        return FileResponse(path,media_type='application/pdf' if pdf else 'text/plain',filename='source.pdf' if pdf else 'source.txt',content_disposition_type='inline' if pdf else 'attachment')

    @app.get('/api/capsule/assets/{name}')
    def asset(name:str):
        folder=root/'reference/hardgel/official_evidence'
        if Path(name).name!=name or Path(name).suffix.lower() not in ('.pdf','.png'):
            raise HTTPException(404,'资料不存在')
        path=folder/name
        if not path.is_file(): raise HTTPException(404,'资料不存在')
        return FileResponse(path)

    dist=root/'apps/web/dist'
    if dist.is_dir():
        app.mount('/assets',StaticFiles(directory=dist/'assets'),name='web-assets')
        @app.get('/')
        def index(): return FileResponse(dist/'index.html',headers={'Cache-Control':'no-cache'})
    return app

app=create_app()
