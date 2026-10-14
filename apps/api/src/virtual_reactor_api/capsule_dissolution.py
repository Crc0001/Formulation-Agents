"""Traceability gates for retrieved table curves, not experimental validation."""
import re
import json

def source_texts(text):
    """Read text leaves of stored patent JSON instead of its escaped serialization."""
    try: value=json.loads(text)
    except (ValueError,TypeError): return [text]
    def leaves(v):
        if isinstance(v,str): return [v]
        if isinstance(v,dict): return [s for x in v.values() for s in leaves(x)]
        if isinstance(v,list): return [s for x in v for s in leaves(x)]
        return []
    return leaves(value)

def matched_table(curve,sources):
    """Recover only an exact time sequence and one consistent numeric column, at the named table."""
    row_table=matched_formulation_rows(curve,sources)
    if row_table:return row_table
    target=re.search(r'(?:TABLE|表)\s*(\d+)',curve.locator,re.I)
    if not target: return None
    matches={}
    for e in sources:
        for text in source_texts(e.get('text','')):
            starts=list(re.finditer(r'\bTABLE\s+(\d+)\b',text,re.I))
            for i,start in enumerate(starts):
                if start[1]!=target[1]: continue
                table=text[start.start():starts[i+1].start() if i+1<len(starts) else len(text)]
                rows=list(re.finditer(r'(?m)^\s*(\d+(?:\.\d+)?)\s*min\s*$',table))
                if [float(r[1]) for r in rows]!=curve.time_min: continue
                values=[]
                for j,row in enumerate(rows):
                    tail=table[row.end():rows[j+1].start() if j+1<len(rows) else len(table)]
                    nums=[]
                    for line in tail.strip().splitlines():
                        if not re.fullmatch(r'\s*\d+(?:\.\d+)?\s*',line): break
                        nums.append(float(line))
                    values.append(nums)
                if not values or not values[0] or len({len(v) for v in values})!=1: continue
                columns=[k for k in range(len(values[0])) if all(abs(values[j][k]-y)<1e-7 for j,y in enumerate(curve.percent))]
                if len(columns)!=1: continue
                # Keep the header and data block verbatim, exclude following narrative.
                end=rows[-1].end()
                final=re.match(r'(?:\s*\d+(?:\.\d+)?[ \t]*\n?){'+str(len(values[-1]))+r'}',table[end:])
                excerpt=table[:end+final.end()] if final else table
                key=re.sub(r'\s+','',excerpt)
                matches[key]=excerpt.strip()
    return next(iter(matches.values())) if len(matches)==1 else None

def matched_formulation_rows(curve,sources):
    """Recover a contiguous numbered Chinese table only with exact batch/row/time binding."""
    label=re.search(r'表\s*(\d+(?:\.[A-Za-z0-9]+)*(?:-\d+)?)',curve.locator)
    if not label:return None
    matches={}
    for source in sources:
        for text in source_texts(source.get('text','')):
            tables=list(re.finditer(r'(?m)^\s*表\s*(\d+(?:\.[A-Za-z0-9]+)*(?:-\d+)?)\b[^\n]*',text))
            for i,start in enumerate(tables):
                if start[1]!=label[1]:continue
                block=text[start.start():tables[i+1].start() if i+1<len(tables) else len(text)]
                header=re.search(r'取样时间[^\n]*\n[ \t]*([\d. \t]+)\r?\n',block)
                if not header or [float(v) for v in header[1].split()]!=curve.time_min:continue
                rows=list(re.finditer(r'(?m)^[ \t]*处方\s*(\d+)[（(]([^）)]+)[）)][ \t]*([\d. \t]+)\r?$',block))
                selected=[r for r in rows if r[2] in curve.sample and r[2] in curve.formula_title and [float(v) for v in r[3].split()]==curve.percent]
                if len(selected)!=1:continue
                excerpt=block[:rows[-1].end()].strip()
                matches[re.sub(r'\s+','',excerpt)]=excerpt
    return next(iter(matches.values())) if len(matches)==1 else None

def validate_curves(report,evidence):
    byid={e['id']:e for e in evidence}; accepted=[]; issues=[]
    normalize=lambda s: re.sub(r'\s+','',s)
    for c in report.dissolution_curves:
        sources=[byid[s] for s in c.source_ids if s in byid and byid[s].get('basis')=='source' and byid[s].get('access') in ('full_text','page_text','imported')]
        formulas=[f for f in report.formulations if f.title==c.formula_title and set(f.source_ids)&set(c.source_ids)]
        quoted=any(normalize(c.table_excerpt) in normalize(t) for e in sources for t in source_texts(e.get('text','')))
        if not quoted:
            recovered=matched_table(c,sources)
            if recovered:
                c=c.model_copy(update={'table_excerpt':recovered})
                quoted=True
        nums={float(n.replace(',','.')) for n in re.findall(r'(?<![\w.])\d+(?:[.,]\d+)?',c.table_excerpt)}
        supported=all(any(abs(v-n)<1e-7 for n in nums) for v in c.time_min+c.percent)
        if len(sources)!=len(c.source_ids) or not formulas or not quoted or not supported:
            issues.append(c.title+'：曲线缺少同处方引用、原文摘录或逐点数字支持，未进入绘图；需回查表格和行列对应。')
        else:
            accepted.append(c)
            if any(y>100 for y in c.percent): issues.append(c.title+'：来源数值超过100%，已保留原值，需核查测定与换算基准。')
    return accepted,issues
