"""Calibration of the existing source first-order structure to actual final batches."""
import json,math,hashlib
import numpy as np
from .native_starch_pair import FOLDER,interpolate

def execute(root,base,variant):
    folder=root/FOLDER
    data=json.loads((folder/'actual-final-batches.json').read_text(encoding='utf-8'))
    expected=json.loads((root/'reference/mecobalamin-validation-20260925/dataset.json').read_text(encoding='utf-8'))['source']['sha256']
    from pathlib import Path
    if hashlib.sha256(Path(data['source_file']).read_bytes()).hexdigest()!=expected:raise ValueError('Actual source changed')
    source=json.loads((folder/'data.json').read_text(encoding='utf-8'))
    x=100*data['formula_mg']['玉米淀粉']/(data['formula_mg']['玉米淀粉']+data['formula_mg']['乳糖'])
    k0=interpolate(source['rows'],x);times=np.array(data['times']);train=np.array(data['water'][:2]);observed=np.array(data['water'][2])
    # No held-out response is used in grid fitting or plateau estimation.
    ks=np.geomspace(.001,10,6001);basis=-np.expm1(-ks[:,None]*times)
    amplitude=(basis@train.sum(axis=0))/(2*(basis*basis).sum(axis=1))
    errors=((amplitude[:,None,None]*basis[:,None,:]-train[None,:,:])**2).mean(axis=(1,2))
    idx=int(np.argmin(errors));k=float(ks[idx]);a=float(amplitude[idx]);pred=a*basis[idx];prior=100*(-np.expm1(-k0*times))
    candidates=ks[np.sqrt(errors)<=math.sqrt(float(errors[idx]))+.1]
    from .retrospective import paired_check
    from .native_starch_pair import coordinates
    dataset=json.loads((root/'reference/mecobalamin-validation-20260925/dataset.json').read_text(encoding='utf-8'))
    target=coordinates(base,variant)
    trend=None
    if target:
        pairs=paired_check(dataset)['contrasts']
        increasing=target['starch_after_mg']>target['starch_before_mg']
        total=sum(i['amount_mg'] for i in variant['ingredients'] if i['role']!='shell')
        before_pct=100*target['starch_before_mg']/total;after_pct=100*target['starch_after_mg']/total
        late=[dataset['times_min'].index(t) for t in (15,20,30)]
        consistent=all(c['delta_q_pp'][j]<0 for c in pairs for j in late)
        trend={'version':'mecobalamin-direction-v1','source':'用户PDF表30/32，三组固定MCC的淀粉增加—乳糖补差对照','times':dataset['times_min'],'contrasts':pairs,'target':target,'before_core_pct':before_pct,'after_core_pct':after_pct,'source_domain_core_pct':[6.38,12.04],'outside_domain':not(6.38<=before_pct<=12.04 and 6.38<=after_pct<=12.04),'late_consistent':consistent,'direction':'降低' if consistent and increasing else '未评估','statement':'预计15—30分钟溶出降低；5—10分钟方向不固定，幅度未校准。' if consistent and increasing else '当前方向需单独核对，不自动反转既有证据。','magnitude_prediction':None,'limitation':'这是同药观察趋势向当前牌号/工艺的条件迁移，不是已确认因果或统计显著性；三组幅度及变化范围不同，不合并为统一斜率。'}
    return {'trend':trend,'baseline_id':base['id'],'variant_id':variant['id'],'source_model':'原配对模块的一阶Q=A(1-exp(-kt))；来源A=100，现用最终实测校准A及k','prior_identity':'按来源配比插值构造的未校准迁移情景，回顾性对照，不是实验前冻结预测','data':data,'train_ids':data['batch_ids'][:2],'holdout_id':data['batch_ids'][2],'k_before':k0,'a_before':100,'k_after':k,'a_after':a,'train_rmse_pp':math.sqrt(float(errors[idx])),'holdout_rmse_before_pp':float(np.sqrt(np.mean((prior-observed)**2))),'holdout_rmse_after_pp':float(np.sqrt(np.mean((pred-observed)**2))),'before':prior.tolist(),'after':pred.tolist(),'observed':observed.tolist(),'residuals_pp':(pred-observed).tolist(),'rate_range_engineering':[float(candidates.min()),float(candidates.max())],'range_definition':'校准RMSE最小值+0.1个百分点的网格候选范围；非统计置信区间；k搜索0.001–10/min','target_variant_prediction':None,'status':'整体释放校准已执行；配比响应斜率未校准，17mg变化方不自动迁移','original_baseline_unchanged':True,'input_sha256':hashlib.sha256(json.dumps({'actual':data,'source':source,'trend_dataset':dataset,'base':base,'variant':variant},sort_keys=True).encode()).hexdigest()}
