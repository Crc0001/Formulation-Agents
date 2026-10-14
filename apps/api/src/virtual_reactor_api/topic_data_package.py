"""Immutable launch availability snapshot, distinguished from report citations."""
import json,hashlib,copy

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def freeze(base,target,evidence,previous=None):
    items=[{'evidence_id':e['id'],'content_hash':digest(e),'snapshot':copy.deepcopy(e)} for e in evidence]
    prior={e['evidence_id']:e['content_hash'] for e in (previous or {}).get('items',[])}
    current={e['evidence_id']:e['content_hash'] for e in items}
    return {'schema_version':1,'baseline_id':base['id'],'baseline_snapshot':copy.deepcopy(base),
        'research_target':copy.deepcopy(target),'items':items,
        'package_hash':digest({'base':base,'target':target,'items':items}),
        'previous_package_id':(previous or {}).get('id'),
        'comparison_status':'可与上轮启动快照比较' if previous else '首个快照或历史轮次无快照，不能重建过去输入',
        'added_ids':[k for k in current if k not in prior],
        'changed_ids':[k for k in current if k in prior and current[k]!=prior[k]],
        'missing_ids':[k for k in prior if k not in current],
        'identity':'启动时可供查阅的资料快照，不等于全部已阅读或已采用'}

def citation_ids(value):
    result=set()
    def walk(v):
        if isinstance(v,dict):
            for k,x in v.items():
                if k in ('source_ids','calculation_ids') and isinstance(x,list):result.update(y for y in x if isinstance(y,str))
                walk(x)
        elif isinstance(v,list):
            for x in v:walk(x)
    walk(value)
    return result
