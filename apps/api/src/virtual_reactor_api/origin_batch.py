"""Persisted, single-dispatch batch research. Reports stay in the normal project stores."""
import asyncio,json
from uuid import uuid4
from pathlib import Path
from .capsule_models import ProjectInput
from .directory_backfill import summary

QUESTIONS={1:'核对正式参比、原研身份、上市历史及各国说明书。区分持有人和生产厂家，按规格列辅料，先用本地目录和已存原文。',2:'追溯原研及相关专利，提取同一实施例定量处方、完整工艺及本剂型性能；不因缺表格漏掉明确文字投料，不编造用量。',3:'比较已存候选与目标说明书辅料、原研关联、定量、工艺和性能，交付可用于试验参考的建议与缺口；不把未读称未公开，不自动冻结。'}

def _row_digest(row):
    """One directory row as labelled fields; never embed the raw attachment text."""
    cells=row.get('cells') or []
    headers=row.get('headers') or ['序号','药品通用名称','英文名','规格','持证商','备注1','备注2']
    pairs=[f'{h}：{c}' for h,c in zip(headers,cells) if str(c).strip()]
    return {'目录行':row.get('entry_number'),'字段':pairs}

def source_digest(source):
    """Directory identity plus the batch's own rows.

    The previous question embedded the whole attachment text (the 102 batch's source
    carried the complete directory dump). That produced a ~106 KB truncated JSON
    payload that made GLM stall past the whole request window; rows are already in the
    registry and the item payload, so only labelled fields are needed here.
    """
    return {k:source.get(k) for k in ('url','title','notice_url','sha256','authority','document_batch','document_title')}

class BatchResearch:
    def __init__(self,root,registry,store,create,submit):
        self.root=Path(root);self.folder=self.root/'data/origin-batch-jobs';self.folder.mkdir(parents=True,exist_ok=True)
        self.registry=registry;self.store=store;self.create=create;self.submit=submit
        self.lock=asyncio.Lock()
    def save(self,s):
        p=self.folder/f"{s['batch']}.json";t=p.with_suffix('.tmp')
        t.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8');t.replace(p)
    def load(self,batch):
        p=self.folder/f'{batch}.json'
        if p.exists():return json.loads(p.read_text(encoding='utf-8'))
        old=sorted((self.root/'reference').glob(f'origin-batch{batch}-research-*/state.json'))
        if old:
            s=json.loads(old[-1].read_text(encoding='utf-8'));s['enabled']=False;s['control_note']='已有后台队列可接续，历史成果保留';return s
        return {'batch':batch,'items':[],'enabled':False,'status':'尚未启动批量研究'}
    def view(self,batch):
        s=self.load(batch);items=s['items'];completed=sum(x['status']=='三阶段已交付，待逐项验收' for x in items)
        from .origin_completion import execution_detail
        supervision_path=self.root/'data/origin-batch-supervision'/f'{batch}.json'
        try:supervision=json.loads(supervision_path.read_text(encoding='utf-8')).get('items',{})
        except (OSError,ValueError):supervision={}
        current=[];details=[];counts={}
        for x in items:
            phases=x.get('phases',[])
            r=self.store.run(phases[-1]['run_id']) if phases else None
            events=[]
            if r:
                with self.store.db() as db:
                    row=db.execute("select kind,payload from events where run_id=? and kind in ('model_error','provider_failure','origin_extract_error','origin_decision_error') order by id desc limit 1",(r['id'],)).fetchone()
                if row:events=[{'kind':row[0],'payload':json.loads(row[1])}]
            detail=execution_detail(x,r,events,supervision.get(x.get('project_id'),{}))
            details.append(detail);counts[detail['code']]=counts.get(detail['code'],0)+1
            if r and r['status'] in ('running','queued'):
                current.append({'name':x['name'],'phase':phases[-1]['phase'],'project_id':x['project_id']})
        status=s['status']
        if not s.get('enabled') and not current and items and completed<len(items) and '队列已结束' in status:
            status='本轮派单已结束，仍有未完成项目'
        return {'batch':batch,'enabled':s.get('enabled',False),'status':status,'total':len(items),'completed':completed,'blocked':sum(x['status']=='中断待核' for x in items),'current':current,'model_profile':s.get('model_profile','astra'),'items':details,'status_counts':counts}
    async def start(self,batch,model):
        async with self.lock:
            s=self.load(batch)
            if not s['items']:
                sources=[x for x in summary(self.registry)['sources'] if x.get('document_batch')==batch and x.get('parsed') and x.get('sha256') and not any(w in (x.get('document_title','')+x.get('title','')) for w in ('征求意见','调出'))]
                if not sources:raise ValueError('此批尚无可读取的正式原表')
                source=sources[0]
                with self.registry.db() as db:rows=[json.loads(r[0]) for r in db.execute('select payload from directory_rows where sha=?',(source['sha256'],))]
                groups={};seen=set()
                for r in rows:
                    if r['entry_number'] in seen:continue
                    seen.add(r['entry_number']);c=r['cells']
                    if len(c)!=7:raise ValueError('原表有未对齐行，请先核对')
                    groups.setdefault(tuple(c[i] for i in (1,2,4)),{'name':c[1],'rows':[],'phases':[],'status':'排队'})['rows'].append(r)
                if not groups:raise ValueError('此批没有可读取的品种行')
                s.update(source=source,items=list(groups.values()))
            s.update(enabled=True,model_profile=model,status='已加入批量队列',external_failure_streak=0);self.save(s)
        return self.view(batch)
    async def retry(self,batch,project_id,model,summary_only=False):
        """Queue a fresh attempt of one failed stage; keep every previous run."""
        async with self.lock:
            s=self.load(batch)
            item=next((i for i in s['items'] if i.get('project_id')==project_id),None)
            if item is None or item['status']!='中断待核' or not item.get('phases'):
                raise ValueError('只能接续指定的中断品种')
            ph=item['phases'][-1]
            if self.store.run(ph['run_id'])['status'] in ('running','queued'):
                raise ValueError('该阶段仍在运行')
            item.setdefault('attempt_history',[]).append(dict(ph))
            item['phases'].pop()
            item['retry_request']={'phase':ph['phase'],'token':str(uuid4()),'previous_run_id':ph['run_id'],'summary_only':summary_only}
            item['status']='排队'
            s.update(enabled=True,model_profile=model,status='已安排失败阶段接续，旧运行保留',external_failure_streak=0)
            self.save(s)
        return self.view(batch)
    async def pause(self,batch):
        async with self.lock:
            s=self.load(batch);s.update(enabled=False,status='已停止后续派单；当前研究完成后保留成果');self.save(s)
        return self.view(batch)
    async def tick(self):
        async with self.lock:
            for path in sorted(self.folder.glob('*.json')):
                s=json.loads(path.read_text(encoding='utf-8'))
                for item in s['items']:
                    if item['status']!='研究中':continue
                    ph=item['phases'][-1];r=self.store.run(ph['run_id']);ph['status']=r['status']
                    if r['status'] in ('running','queued'):continue
                    from .origin_completion import delivery_issues
                    blockers=delivery_issues(r.get('report'),ph['phase'])
                    ph['delivery_issues']=blockers
                    if r['status'] not in ('partial','completed') or r.get('error') or blockers:
                        item['status']='中断待核';s['external_failure_streak']=s.get('external_failure_streak',0)+1
                    else:
                        item['status']='三阶段已交付，待逐项验收' if ph['phase']==3 else '排队';s['external_failure_streak']=0
                if s.get('external_failure_streak',0)>=2:s.update(enabled=False,status='连续两项中断，已停止派单，请查看具体品种')
                self.save(s)
                if not s.get('enabled'):continue
                with self.store.db() as db:allruns=[json.loads(r[0]) for r in db.execute('select payload from runs')]
                if any(r['status'] in ('running','queued') for r in allruns):continue
                item=next((i for i in s['items'] if i['status']=='排队'),None)
                if not item:
                    incomplete=any(i['status']=='中断待核' for i in s['items'])
                    s.update(enabled=False,status='本轮派单已结束，仍有未完成项目' if incomplete else '三阶段报告均已交付，待科学核验');self.save(s);continue
                batch=s['batch'];name=f"第{batch}批原研库 · {item['name']} · {item['rows'][0]['entry_number']}"
                if not item.get('project_id'):
                    p=next((p for p in self.store.projects() if p['name']==name),None)
                    if p is None:p=self.create(ProjectInput(name=name,api=item['name'],market='中国参比及对应原研上市地区',strength='；'.join(r['cells'][3] for r in item['rows']),strength_basis='目录原文，未换算',dosage_form=item['name']))
                    item['project_id']=p['id'];self.save(s)
                retry=item.get('retry_request')
                phase=retry['phase'] if retry else len(item['phases'])+1;marker=f"【{batch}批整批建档:{item['rows'][0]['entry_number']}:阶段{phase}】"
                if retry:marker+='【接续尝试:'+retry['token']+'】'
                runs=self.store.rows('runs',item['project_id']);r=next((r for r in reversed(runs) if marker in r.get('message','')),None)
                if r is None and not retry:
                    from .origin_stages import origin_stage
                    r=next((x for x in reversed(runs) if origin_stage(x.get('message',''))==phase),None)
                if r is None:
                    question=('【接续：汇总】' if retry and retry['summary_only'] else '')+f'【01阶段{phase}】'+marker+QUESTIONS[phase]+'\n本批原件身份与目标行（原表已归档，不在此重复整份附件正文；需要时用工具读原文）：'+json.dumps({'source':source_digest(s['source']),'rows':[_row_digest(r) for r in item['rows']]},ensure_ascii=False)
                    r=await self.submit(item['project_id'],question,s['model_profile'])
                item.pop('retry_request',None)
                item['phases'].append({'phase':phase,'run_id':r['id'],'status':r['status']});item['status']='研究中';s['status']='研究进行中';self.save(s);return
    async def loop(self):
        while True:
            try:await self.tick()
            except Exception as ex:
                for p in self.folder.glob('*.json'):
                    s=json.loads(p.read_text(encoding='utf-8'))
                    if s.get('enabled'):s.update(enabled=False,status='派单异常，已停止并保留进度：'+type(ex).__name__);self.save(s)
            await asyncio.sleep(5)

