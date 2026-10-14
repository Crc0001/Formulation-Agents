"""Explicit, idempotent import of the previously inspected research case."""
import json
from pathlib import Path
from .capsule_models import ProjectInput,EvidenceInput,TaskInput
from .capsule_store import Store

PID='amoxicillin-cn-250'

def import_case(store:Store,root:Path):
    if any(p['id']==PID for p in store.projects()): return
    ref=root/'reference/hardgel'
    if not ref.is_dir(): return
    state=json.loads((ref/'amoxicillin-cn-250-project.json').read_text(encoding='utf-8'))
    dossier=state['originator_dossier']
    store.create_project(ProjectInput(name='阿莫西林胶囊 · 中国 · 250 mg',api='阿莫西林',market='中国',strength='250 mg',strength_basis='每粒按阿莫西林计',dosage_form='普通释放硬胶囊'),PID)
    run=store.create_run(PID,'导入Hardgel已归档的阿莫西林250 mg资料（不是本次联网检索）')
    for row in json.loads((ref/'amoxicillin-cn-250-records.json').read_text(encoding='utf-8')):
        r=json.loads(row['payload']);f=r['fields']
        if r['kind']=='decision':
            store.add_task(PID,TaskInput(title=r['title'],question=f['question'],experiment=f['experiment'],endpoint=f['endpoint']))
            continue
        fields=dict(f)
        if f.get('source_image'): fields['image']='/api/capsule/assets/'+Path(f['source_image']).name
        store.add_evidence(PID,EvidenceInput(section='dissolution' if r['kind']=='dissolution' else 'formulation',title=r['title'],text=f.get('evidence','')+'\n'+f.get('applicability',''),basis='image_estimate' if 'curve_csv' in f else 'source',source_url=f.get('source_url',''),locator=f.get('locator','历史记录'),applicability=f.get('applicability','原项目导入，待复核'),access='imported',product=f.get('product',''),strength=f.get('strength',''),market=f.get('market',''),document_version='版本见原文定位',fields=fields),run['id'])
    sources={s['source_id']:s for s in dossier['sources']}
    for section,title,text,source_id,basis in [
        ('reference','参比尚未锁定','中国2017年第三批历史公告3-17收载Amoxil 0.25 g。当前资格与变更待核验；日本Sawacillin资料不能自动替代目标参比。','CN3','source'),
        ('process','商业工艺尚未确认','现有公开说明书不能证明使用直接填充、干法或湿法。US6352720B1实例3与7是500 mg胶囊技术方案，不是本项目商业工艺证明。','PAT','unknown'),
        ('comparison','先验证直接填充可行性','拟优先验证直接混合填充；仅当流动、装量或均匀性经优化仍不能达到预设终点时比较干法。湿法须先有必要性和稳定性依据。原研内部选择原因未知。','IF','hypothesis'),
        ('excipients','原研辅料等级与用量缺口','已公开内容物硬脂酸镁，但用量、粒径、比表面积、供应商和等级未知。明胶及十二烷基硫酸钠属于壳组成，不能并入填充物。拟按药用标准、功能性及溶出敏感性筛选。','IF','hypothesis')]:
        store.add_evidence(PID,EvidenceInput(section=section,title=title,text=text,basis=basis,source_url=sources[source_id]['url'],locator='历史项目已核验的公告或IF/专利，细节见归档',applicability='中国250 mg项目；历史研究导入不代表重新核验',access='imported'),run['id'])
    store.event(run['id'],'legacy_import',{'origin_id':state['thread_id'],'origin_updated_at':state['updated_at'],'files':['amoxicillin-cn-250-project.json','amoxicillin-cn-250-records.json'],'original_report':state['answer']})
    store.finish(run['id'],'completed')
