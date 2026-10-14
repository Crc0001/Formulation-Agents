"""Deterministic source/report coverage checks, never a scientific equivalence check."""
import json
import re

def source_text(value):
    try:
        obj=json.loads(value)
    except (ValueError,TypeError):return value
    def leaves(x):
        if isinstance(x,str):return [x]
        if isinstance(x,list):return [s for v in x for s in leaves(v)]
        if isinstance(x,dict):return [s for v in x.values() for s in leaves(v)]
        return []
    return '\n'.join(leaves(obj))

def patent_id(e):
    text=e.get('source_url','')+' '+e.get('title','')
    match=re.search(r'\b(CN\s*\d{7,12}\s*[AB]\d?|US\s*\d{6,12}\s*[AB]\d?)\b',text,re.I)
    return re.sub(r'\s','',match[1]).upper() if match else None

def example_id(text):
    m=re.search(r'(实施例|对照例|对比例)\s*(\d+)(?!\d)',text)
    return m[1]+m[2] if m else None

def audit_patents(report,evidence):
    grouped={};byid={e['id']:e for e in evidence}
    for e in evidence:
        doc=patent_id(e)
        if not doc or e.get('basis') not in ('source','image_estimate') or e.get('access')=='snippet':continue
        text=source_text(e['text'])
        # Headings only, not a passing reference to another example in prose.
        for m in re.finditer(r'(?:^|\n|\[\d{4}\])\s*(实施例|对照例|对比例)\s*(\d+)(?!\d)',text):
            name=m[1]+m[2];key=(doc,name)
            item=grouped.setdefault(key,{'patent':doc,'example':name,'evidence_ids':[],'locator':e.get('locator',''),'status':'missing'})
            if e['id'] not in item['evidence_ids']:item['evidence_ids'].append(e['id'])
    # Only audit patents actually used for this report's formulation/process claims.
    used={patent_id(byid[s]) for f in [*report.formulations,*report.processes] for s in f.source_ids if s in byid}
    result=[]
    for (doc,name),item in grouped.items():
        if doc not in used:continue
        matches=[f for f in report.formulations if example_id(f.title)==name and any(patent_id(byid[s])==doc for s in f.source_ids if s in byid)]
        if matches:
            quantitative=any(any(c.compartment=='fill' for c in f.components) and all(c.amount_mg is not None or c.batch_amount is not None or c.percent is not None for c in f.components if c.compartment=='fill') for f in matches)
            item['status']='recorded' if quantitative else 'quantity_unresolved'
        result.append(item)
    return sorted(result,key=lambda x:(x['patent'],x['example']))

def audit_gaps(rows):
    return [f"专利收录核对：{x['patent']} {x['example']}："+('已发现但未收录处方；回读对应实施例和图片表，不得写成原文无处方。' if x['status']=='missing' else '已收录组成但定量未解决；核对原表/图像，不能以程序未读全作为不推荐的药学理由。') for x in rows if x['status']!='recorded']
