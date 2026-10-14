"""Reuse archived research only for exactly matching saved conditions."""
import json,hashlib,asyncio

def signature(v):
    required=('baseline_id','ingredients','method','process','api_particle','mass_basis','total_policy')
    if any(k not in v for k in required):return None
    fields={k:value for k,value in v.items() if k not in ('id','title','created_at','version')}
    fields['ingredients']=sorted(fields['ingredients'],key=lambda x:x['id'])
    return hashlib.sha256(json.dumps(fields,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def reuse_bundle(variant,variants,pairs,calibrations):
    sig=signature(variant)
    ids={v['id'] for v in variants if sig and signature(v)==sig}
    return {'variant_id':variant['id'],'matching_variant_ids':sorted(ids),
            'pair_studies':[r for r in pairs if r['variant_id'] in ids],
            'final_calibrations':[r for r in calibrations if r['variant_id'] in ids],
            'limitation':'仅因保存的组成、品牌规格、工艺、方法和基准完全一致而展示历史研究。未知条件仍未知，不代表物理批次等效。最终实际处方校准不能作为17mg淀粉方案已验证的定量预测；同药配对趋势按原适用范围使用。'}

async def finish_missing_output(output,synthesize,checkpoint,notify):
    if output is not None:return output,False
    notify('report_synthesis',{'reason':'最终结构化报告缺失，依据已存资料补做一次汇总'})
    try:
        result=await synthesize()
        if result is None:raise ValueError('empty synthesis')
        return result,True
    except asyncio.CancelledError:raise
    except Exception as ex:
        saved=checkpoint()
        notify('report_synthesis_incomplete',{'error_type':type(ex).__name__,'checkpoint_retained':bool(saved)})
        if not saved:raise
        from .capsule_models import ResearchReport
        report=ResearchReport.model_validate(saved)
        report.gaps=list(dict.fromkeys([*report.gaps,'最终结构化汇总未完成；保留阶段稿及已存计算，不能视为最终结论。']))
        return report,True
