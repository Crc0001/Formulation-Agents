"""04 summary input: frozen task and referenced records, not the whole archive."""
import json,re
from .calculation_handoff import saved_calculations
from .table_vision import accepted_table

def summary_payload(payload,evidence,run_id):
    message=payload['request']; task={}
    for label in ('冻结基准','变化方案'):
        try:task[label]=json.JSONDecoder().raw_decode(message.split('\n'+label+'：',1)[1])[0]
        except (IndexError,ValueError):return payload # Preserve unfamiliar legacy requests.
    task['问题']=message.split('\n问题：',1)[-1].split('\n',1)[0]
    checkpoint=payload.get('checkpoint')
    # A saved judgment defines the citations; no report means keep the handoff references.
    calculations=saved_calculations(evidence,run_id,'' if checkpoint else message,checkpoint)
    ids=set(re.findall(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}',json.dumps([checkpoint,calculations],ensure_ascii=False)))
    selected=[]
    for e in evidence:
        if e['id'] not in ids:continue
        # Calculations are carried exactly once, with complete numerical records.
        if e['id'] in {c['id'] for c in calculations}:continue
        item={k:e.get(k) for k in ('id','title','basis','access','source_url','locator')}
        item['text']=e.get('text','')[:6000]
        item['text_truncated']=len(e.get('text',''))>6000
        item['machine_table_verified']=accepted_table(e,evidence)
        selected.append(item)
    return {**payload,'request':task,'sources':selected,'saved_calculations':calculations,
        'archive_notice':'仅本次引用资料；截取文本不代表全文。原始资料完整保留，机器一致表仍为image_estimate；不得声称已人工核验。'}
