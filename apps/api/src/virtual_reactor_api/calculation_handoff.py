"""Carry actual saved calculations into report recovery, without recomputation."""
import json
import re

KEYS = ('pair_difference_model_json', 'source_metric_json', 'source_response_model_json',
        'source_curve_model_json', 'digitized_chart_json', 'excipient_stage_json',
        'mechanistic_chain_json', 'effective_rate_transfer_json')

def variant_identity(run):
    try:
        value=json.JSONDecoder().raw_decode(run.get('message','').split('\n变化方案：',1)[1])[0]
        return value['id'], value['baseline_id']
    except (ValueError, KeyError, IndexError, TypeError):
        return None

def continuation_package(runs, evidence, project_id, variant, previous_id=None):
    """Same-project, same saved variant only. Never inherit a different recipe."""
    candidates=[r for r in runs if r.get('project_id')==project_id
                and variant_identity(r)==(variant['id'],variant['baseline_id'])]
    if previous_id:
        previous=next((r for r in candidates if r['id']==previous_id),None)
        if previous is None:raise ValueError('接续任务必须属于当前项目、同一冻结基准和保存方案')
    else:
        previous=max(candidates,key=lambda r:r.get('created_at',''),default=None)
    if previous is None:raise ValueError('当前保存方案没有可接续的研究，请先启动研究')
    if previous['status'] in ('queued','running'):raise ValueError('原任务仍在运行，请等待结束后接续')
    report=previous.get('report')
    calculations=saved_calculations(evidence,previous['id'],previous.get('message',''),report)
    required=set()
    def collect(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('calculation_ids','calculation_evidence_ids') and isinstance(item,list):
                    required.update(x for x in item if isinstance(x,str))
                else:collect(item)
        elif isinstance(value,list):
            for item in value:collect(item)
    collect(report)
    missing=sorted(required-{e['id'] for e in calculations})
    return {'previous_run_id':previous['id'],'baseline_id':variant['baseline_id'],
            'variant_id':variant['id'],'previous_report':report,
            'calculation_ids':[e['id'] for e in calculations],
            'missing_calculation_ids':missing,
            'instruction':'继承上一轮报告，优先解读已存计算。缺失ID才作为附件缺口，不重复计算，不修改原记录。'}

def saved_calculations(evidence, run_id, message, checkpoint=None):
    references = set(re.findall(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}',
                               message + json.dumps(checkpoint, ensure_ascii=False)))
    related = references | {run_id}
    return [dict(id=e['id'], run_id=e.get('run_id'), basis=e['basis'], title=e['title'],
                 source_url=e.get('source_url'),
                 records={k:e['fields'][k] for k in KEYS if k in e.get('fields', {})})
            for e in evidence if (e.get('run_id') in related or e['id'] in references)
            and any(k in e.get('fields', {}) for k in KEYS)]
