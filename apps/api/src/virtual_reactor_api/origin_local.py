"""Bind hash-verified shared directory originals to a project's research evidence."""
import hashlib,json,re
from .capsule_models import EvidenceInput
from .directory_backfill import search_rows

def preload(registry,store,pid):
    project=store.project(pid)
    normal=lambda s:re.sub(r'\s+','',s or '').casefold()
    name=normal(project['api'])
    matches=[r for r in search_rows(registry,project['api']) if len(r.get('cells',[]))>=2 and normal(r['cells'][1])==name]
    existing=store.rows('evidence',pid); grouped={};records=[]
    for r in matches:grouped.setdefault(r['source_sha256'],[]).append(r)
    for sha,rows in grouped.items():
        path=registry.folder/sha
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:continue
        url=rows[0].get('source_url','')
        if not url.startswith(('https://','http://')):continue
        key=sha+':'+name
        e=next((e for e in existing if e.get('fields',{}).get('local_directory_key')==key),None)
        if e is None:
            text='来源标题：'+rows[0].get('source_title','')+'\n本地原始目录机器转录；列对应待核，不等于现行资格已核实。\n'+'\n'.join(' | '.join(r['cells']) for r in rows)
            e=store.add_evidence(pid,EvidenceInput(section='reference',title='自建库目录原文：'+project['api'],text=text,basis='source',source_url=url,locator='；'.join(f"表{r['table']}行{r['row']}（{r['entry_number']}）" for r in rows),access='imported',applicability='同名条目；规格、持有人和历史版本逐条核对，不自动认定现行参比资格。',fields={'local_directory_key':key,'source_document_sha256':sha,'identity_priority':'true','identity_excerpt':text,'extraction_status':'machine_transcription_pending_review'}))
        records.append({'evidence_id':e['id'],'sha256':sha,'entries':[r['entry_number'] for r in rows],'rows':[r['cells'] for r in rows]})
    return {'directory_sources':records,'matching_rule':'通用名去空白精确匹配，规格及版本逐行保留；无精确匹配不借用其他药物','project_source_count':len(store.rows('evidence',pid))}
