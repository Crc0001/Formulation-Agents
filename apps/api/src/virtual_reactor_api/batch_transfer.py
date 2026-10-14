"""Portable, immutable agent01 batch snapshots; no configuration or queue execution."""
import io,json,re,zipfile,hashlib,sqlite3
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL,UUID
from .capsule_store import now,clean
from .capsule_models import Project,Evidence,Run
LIMIT=1024*1024*1024

def digest(b):return hashlib.sha256(b).hexdigest()
def packed(x):return json.dumps(x,ensure_ascii=False,sort_keys=True).encode('utf-8')
def safe(x):
    x=clean(x)
    if isinstance(x,str):return re.sub(r'\bsk-[A-Za-z0-9_-]{16,}', '[redacted]',x)
    if isinstance(x,list):return [safe(v) for v in x]
    if isinstance(x,dict):return {k:safe(v) for k,v in x.items()}
    return x

class BatchTransfer:
    def __init__(self,root,stores,queue):
        self.root=root;self.stores=stores;self.store=stores['origin'];self.queue=queue
        self.folder=root/'data/batch-transfers';self.folder.mkdir(parents=True,exist_ok=True)
    def snapshot(self,batch):
        if batch<1:raise ValueError('批次不正确')
        state=self.queue.load(batch);pids={x.get('project_id') for x in state['items']}
        with self.store.db() as c:
            c.execute('BEGIN')
            projects=[json.loads(r[0]) for r in c.execute('select payload from projects')]
            projects=[p for p in projects if p['id'] in pids or p['name'].startswith(f'第{batch}批原研库 · ')]
            items=[]
            for p in projects:
                item={'project':p}
                for table in ('evidence','runs'):
                    item[table]=[json.loads(r[0]) for r in c.execute(f'select payload from {table} where project_id=?',(p['id'],))]
                items.append(item)
        if not items:raise ValueError('该批尚无已保存研究成果')
        m=safe({'format':'origin-batch-results-v1','batch':batch,'exported_at':now(),'source':state.get('source',{}),'projects':items})
        blobs={};missing=[]
        for h in sorted(set(re.findall(r'\b[0-9a-f]{64}\b',json.dumps(m)))):
            f=self.root/'data/documents'/h
            if f.is_file() and not f.is_symlink():blobs[h]=f
        for item in items:
            for e in item['evidence']:
                h=e.get('fields',{}).get('sha256','')
                if re.fullmatch('[0-9a-f]{64}',h) and h not in blobs:missing.append(h)
        m['missing_files']=sorted(set(missing));m['files']=sorted(blobs)
        if len(packed(m))+sum(f.stat().st_size for f in blobs.values())>LIMIT:raise ValueError('成果包超过1GB，请联系维护者分包')
        return m,blobs
    def info(self,m):
        return {'batch':m['batch'],'exported_at':m['exported_at'],'products':len(m['projects']),'reports':sum(bool(r.get('report')) for p in m['projects'] for r in p['runs']),'evidence':sum(len(p['evidence']) for p in m['projects']),'active':sum(r['status'] in ('running','queued') for p in m['projects'] for r in p['runs']),'files':len(m['files']),'missing_files':len(m['missing_files']),'names':[p['project']['name'] for p in m['projects']]}
    def export(self,batch):
        m,blobs=self.snapshot(batch);b=io.BytesIO()
        with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('manifest.json',packed(m))
            for h,v in blobs.items():
                if digest(v.read_bytes())!=h:raise ValueError('原文附件校验失败：'+h)
                z.write(v,'documents/'+h)
        return b.getvalue()
    def export_file(self,batch):
        from uuid import uuid4
        m,blobs=self.snapshot(batch);out=self.folder/('export-'+str(uuid4())+'.zip')
        try:
            with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
                z.writestr('manifest.json',packed(m))
                for h,v in blobs.items():
                    if digest(v.read_bytes())!=h:raise ValueError('原文附件校验失败：'+h)
                    z.write(v,'documents/'+h)
            return out
        except Exception:
            out.unlink(missing_ok=True);raise
    def read(self,data):
        if len(data)>LIMIT:raise ValueError('文件超过1GB')
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names=z.namelist()
                if len(names)!=len(set(names)) or sum(f.file_size for f in z.infolist())>LIMIT:raise ValueError('文件重复或解压后过大')
                if any(n!='manifest.json' and not re.fullmatch(r'documents/[0-9a-f]{64}',n) for n in names):raise ValueError('包中含不支持的路径')
                m=json.loads(z.read('manifest.json'))
                if m['format']!='origin-batch-results-v1' or type(m['batch'])!=int or m['batch']<1:raise ValueError('不是受支持的批次成果包')
                seen=set()
                for p in m['projects']:
                    for record in [p['project'],*p['evidence'],*p['runs']]:
                        UUID(record['id'])
                        if record['id'] in seen:raise ValueError('成果包含重复编号')
                        seen.add(record['id'])
                    Project.model_validate(p['project'])
                    for table,model in [('evidence',Evidence),('runs',Run)]:
                        ids=set()
                        for r in p[table]:
                            model.model_validate(r)
                            if r['project_id']!=p['project']['id'] or r['id'] in ids:raise ValueError('记录归属或编号有误')
                            ids.add(r['id'])
                blobs={h:z.read('documents/'+h) for h in m['files']}
                if any(digest(v)!=h for h,v in blobs.items()):raise ValueError('附件校验失败')
                self.info(m)
                return m,blobs
        except (KeyError,TypeError,zipfile.BadZipFile,UnicodeError) as ex:raise ValueError('成果包不完整或格式不正确') from ex
    def preview(self,data):
        m,_=self.read(data);token=digest(data);path=self.folder/(token+'.zip');path.write_bytes(data)
        existing={self.identity(p) for p in self.store.projects()}
        info=self.info(m);info.update(token=token,existing=sum(self.identity(p['project']) in existing for p in m['projects']))
        return info
    def identity(self,p):return tuple(p.get(k,'') for k in ('name','api','market','strength','strength_basis','dosage_form'))
    def apply(self,token):
        if not re.fullmatch('[0-9a-f]{64}',token):raise ValueError('请选择成果文件')
        path=self.folder/(token+'.zip');done=self.folder/(token+'.json')
        if done.exists():return {**json.loads(done.read_text(encoding='utf-8')),'duplicate':True}
        m,blobs=self.read(path.read_bytes());links=[];added=0
        backup=self.folder/('before-'+token+'.sqlite3')
        with self.store.db() as c,sqlite3.connect(backup) as target:c.backup(target)
        docs=self.root/'data/documents';docs.mkdir(parents=True,exist_ok=True)
        for h,v in blobs.items():
            target=docs/h
            if target.exists() and digest(target.read_bytes())!=h:raise ValueError('本机同名附件校验失败')
            if not target.exists():target.write_bytes(v)
        with self.store.db() as c:
            c.execute('BEGIN IMMEDIATE')
            existing=[json.loads(x[0]) for x in c.execute('select payload from projects')]
            for item in m['projects']:
                p=item['project'];match=next((x for x in existing if self.identity(x)==self.identity(p)),None)
                pid=match['id'] if match else str(uuid5(NAMESPACE_URL,'batch-project:'+repr(self.identity(p))))
                np={**p,'id':pid};c.execute('insert or ignore into projects values(?,?)',(pid,packed(np).decode()));existing.append(np)
                mapping={p['id']:pid};records=[]
                for table in ('evidence','runs'):
                    for r in item[table]:
                        old=c.execute(f'select payload from {table} where id=?',(r['id'],)).fetchone()
                        identical=old and json.loads(old[0])==r and pid==p['id']
                        nid=r['id'] if identical else str(uuid5(NAMESPACE_URL,table+':'+pid+':'+digest(packed(r))))
                        mapping[r['id']]=nid;records.append((table,r,nid,identical))
                def remap(x):
                    if isinstance(x,dict):return {k:remap(v) for k,v in x.items()}
                    if isinstance(x,list):return [remap(v) for v in x]
                    if isinstance(x,str):
                        for old,new in mapping.items():x=x.replace(old,new)
                    return x
                for table,r,nid,identical in records:
                    if identical:continue
                    v=remap(safe(r));v['id']=nid;v['project_id']=pid
                    if table=='runs':
                        if v['status'] in ('running','queued'):
                            v['status']='partial';v['error']='导入的是研究中途快照；未在本机启动任务'
                        v['message']='【外部成果导入；原始运行 '+r['id']+'】'+v.get('message','')
                        cur=c.execute('insert or ignore into runs values(?,?,?,?)',(nid,pid,v['status'],packed(v).decode()))
                    else:cur=c.execute('insert or ignore into evidence values(?,?,?)',(nid,pid,packed(v).decode()))
                    added+=cur.rowcount
                links.append({'id':pid,'name':p['name']})
        # Companion stores need the project shell for the existing full-project reader.
        for key,store in self.stores.items():
            if key=='origin':continue
            with store.db() as c:
                for link in links:
                    p=self.store.project(link['id']);c.execute('insert or ignore into projects values(?,?)',(p['id'],packed(p).decode()))
        result={**self.info(m),'added_records':added,'projects':links,'imported_at':now(),'duplicate':False}
        done.write_bytes(packed(result));return result
    def history(self):
        return [json.loads(p.read_text(encoding='utf-8')) for p in self.folder.glob('*.json')]

def install_routes(app,transfer):
    import asyncio
    from fastapi import Request,HTTPException
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask
    lock=asyncio.Lock()
    @app.get('/api/origin-registry/batches/{batch}/export-preview')
    def export_preview(batch:int):
        try:return transfer.info(transfer.snapshot(batch)[0])
        except ValueError as ex:raise HTTPException(422,str(ex)) from None
    @app.get('/api/origin-registry/batches/{batch}/export')
    def export_batch(batch:int):
        try:data=transfer.export_file(batch)
        except ValueError as ex:raise HTTPException(422,str(ex)) from None
        return FileResponse(data,media_type='application/zip',filename=f'origin-batch-{batch}.zip',headers={'Cache-Control':'no-store'},background=BackgroundTask(data.unlink,missing_ok=True))
    @app.post('/api/origin-registry/import-preview')
    async def import_preview(request:Request):
        data=bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data)>LIMIT:raise HTTPException(413,'文件超过1GB')
        try:return await asyncio.to_thread(transfer.preview,bytes(data))
        except ValueError as ex:raise HTTPException(422,str(ex)) from None
    @app.post('/api/origin-registry/import/{token}')
    async def import_batch(token:str):
        async with lock:
            try:return await asyncio.to_thread(transfer.apply,token)
            except FileNotFoundError:raise HTTPException(404,'预览文件已不存在，请重新选择文件') from None
            except ValueError as ex:raise HTTPException(422,str(ex)) from None
    @app.get('/api/origin-registry/imports')
    def imports():return transfer.history()
