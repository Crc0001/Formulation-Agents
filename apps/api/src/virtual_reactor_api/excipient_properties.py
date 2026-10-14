"""Versioned local workbook library; imported observations never become adopted parameters."""
import hashlib,json,sqlite3,zipfile,re,shutil
from pathlib import Path
from datetime import datetime,timezone
from xml.etree import ElementTree as ET

NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def workbook_rows(path):
    with zipfile.ZipFile(path) as z:
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=[''.join(e.itertext()) for e in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',NS)]
        rel={e.attrib['Id']:e.attrib['Target'] for e in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        for sheet in ET.fromstring(z.read('xl/workbook.xml')).findall('m:sheets/m:sheet',NS):
            target=rel[sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
            name=target.lstrip('/') if target.startswith('/') else 'xl/'+target
            for row in ET.fromstring(z.read(name)).findall('m:sheetData/m:row',NS):
                cells={}
                for c in row.findall('m:c',NS):
                    v=c.find('m:v',NS);value=v.text if v is not None else ''
                    if c.attrib.get('t')=='s':value=strings[int(value)]
                    elif c.attrib.get('t')=='inlineStr':value=''.join(c.find('m:is',NS).itertext())
                    if value:cells[re.sub(r'\d','',c.attrib['r'])]=value
                if int(row.attrib['r'])>1 and cells.get('C') and cells.get('D'):
                    yield sheet.attrib['name'],int(row.attrib['r']),cells

def observation(sheet,row,c):
    flags=[];value=c.get('U','');unit=c.get('V','');text=c.get('W','');metric=c.get('K','')
    if not value and text in ('','/'):flags.append('未记录检测结果；方法和限度不能代替结果')
    if value and not unit:flags.append('实际结果单位未填；不得自动换算百分数或沿用指标单位')
    if metric=='湿润角' and value and float(value)<0.01:flags.append('接触角数值异常，须核对原始记录')
    if metric=='K值' and ('滴定' in c.get('Z','') or unit=='ml'):flags.append('指标与滴定记录错配，禁止用于模型')
    if metric=='吸水率' and '高湿' in c.get('Z',''):flags.append('方法为高湿吸湿，不是液体渗透或浸水吸液')
    if metric=='结晶性' and ('2θ' in text or '2θ' in text.replace(' ','') or '角' in text):flags.append('仅峰位置，不能作为结晶度百分数')
    return {'id':f'{sheet}:{row}','sheet':sheet,'row':row,'metric':metric,'value':value,'unit':unit,'text':text,'method':c.get('P',''),'conditions':c.get('Z',''),'standard':c.get('X',''),'flags':flags,'status':'待核对' if flags else '已录入，适用性待确认','model_eligible':False,'raw':c}

def import_workbook(root,source):
    root=Path(root);source=Path(source);digest=hashlib.sha256(source.read_bytes()).hexdigest()
    dest=root/'reference/excipient-properties'/f'{digest}.xlsx';dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():shutil.copy2(source,dest)
    grouped={}
    for sheet,row,c in workbook_rows(dest):
        key=sheet+':'+c['C']
        m=grouped.setdefault(key,{'id':digest[:16]+':'+key,'source_material_id':c['C'],'name':c['D'],'manufacturer':c.get('E',''),'grade':c.get('F',''),'batch':c.get('G',''),'cas':c.get('H',''),'function':c.get('I',''),'observations':[]})
        m['observations'].append(observation(sheet,row,c))
    meta={'id':digest,'filename':source.name,'archive':dest.relative_to(root).as_posix(),'imported_at':datetime.now(timezone.utc).isoformat(),'material_count':len(grouped),'name_count':len({m['name'] for m in grouped.values()}),'record_count':sum(len(m['observations']) for m in grouped.values()),'status':'用户提供检测记录；未独立核验，未采纳为模型参数'}
    (root/'data').mkdir(exist_ok=True)
    with sqlite3.connect(root/'data/excipient-properties.sqlite3') as db:
        db.execute('CREATE TABLE IF NOT EXISTS imports(id TEXT PRIMARY KEY,payload TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS materials(id TEXT PRIMARY KEY,import_id TEXT,payload TEXT)')
        if db.execute('SELECT 1 FROM imports WHERE id=?',(digest,)).fetchone():return meta
        db.execute('INSERT INTO imports VALUES(?,?)',(digest,json.dumps(meta,ensure_ascii=False)))
        db.executemany('INSERT INTO materials VALUES(?,?,?)',[(m['id'],digest,json.dumps(m,ensure_ascii=False)) for m in grouped.values()])
    return meta

def library(root):
    path=Path(root)/'data/excipient-properties.sqlite3'
    if not path.exists():return {'imports':[],'materials':[]}
    with sqlite3.connect(path) as db:
        return {'imports':[json.loads(r[0]) for r in db.execute('SELECT payload FROM imports ORDER BY rowid')],'materials':[json.loads(r[0]) for r in db.execute('SELECT payload FROM materials ORDER BY rowid')]}

def research_context(root,ingredients,store=None,pid=None):
    data=library(root);names={i['name'] for i in ingredients if i.get('role')=='excipient'}
    selected=[]
    for m in data['materials']:
        matches=[n for n in names if n==m['name'] or (n=='特白玉米淀粉' and m['name']=='玉米淀粉')]
        if not matches:continue
        selected.append({k:m[k] for k in ['id','name','manufacturer','grade','batch']}|{'matched_names':matches,'identity':'仅名称候选匹配；厂家、规格、批号和方法仍需核对，不是当前处方实测','observations':[{k:o[k] for k in ['sheet','row','metric','value','unit','text','method','conditions','flags','model_eligible']} for o in m['observations']]})
    if not selected:return ''
    if store is not None:
        from .capsule_models import EvidenceInput
        for meta in data['imports']:
            archive=Path(root)/meta['archive']
            if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest()!=meta['id']:
                continue
            subset=[m for m in selected if m['id'].startswith(meta['id'][:16]+':')]
            if not subset:continue
            content=json.dumps(subset,ensure_ascii=False)
            fingerprint=hashlib.sha256(content.encode()).hexdigest()
            existing=next((e for e in store.rows('evidence',pid) if e.get('fields',{}).get('workbook_subset_sha256')==fingerprint and e.get('fields',{}).get('verified_workbook_sha256')==meta['id']),None)
            if existing is None:
                existing=store.add_evidence(pid,EvidenceInput(section='excipients',title=meta['filename']+' · 当前辅料候选原始记录',text=content,basis='measurement',access='imported',locator='各条记录的sheet与row定位；原始XLSX按SHA256校验',applicability='用户提供的异批原粉检测记录；未独立核验，不是当前处方实测，不自动成为模型参数',fields={'verified_workbook_sha256':meta['id'],'workbook_subset_sha256':fingerprint,'archive':meta['archive'],'model_eligible':'false'}))
            meta['source_id']=existing['id']
            for m in subset:m['source_id']=existing['id']
    return '\n本地辅料物性库候选记录（引用物料ID、工作表和行号；保留来源身份）：'+json.dumps({'imports':data['imports'],'materials':selected},ensure_ascii=False)+'\n这些是用户提供的原始记录，不是已校准模型参数。必须报告匹配和不匹配条件；flags所指异常不可用于计算。无批号、无单位不可猜测。不得将原粉性质直接视为颗粒或片剂性质，不把候选批次当作当前处方批次，不从Carr指数生成溶出系数。'
