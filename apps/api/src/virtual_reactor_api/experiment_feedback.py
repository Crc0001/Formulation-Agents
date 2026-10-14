"""Immutable experimental return contract; no automatic parameter adoption."""
from copy import deepcopy

def feedback(anchor):
    variant=anchor['variant_snapshot']
    return deepcopy({
        'schema':'experiment-return-v1','anchor_id':anchor['id'],
        'baseline_id':variant['baseline_id'],'variant_id':variant['id'],
        'variant_snapshot':variant,'batch':anchor['batch'],'method':anchor['method'],
        'observed_points':anchor['points'],'units':{'time':'min','response':'%'},
        'prior_prediction':anchor.get('prior'),
        'local_fit':{k:anchor.get(k) for k in ('model','tau_min','beta','fit_rmse_pp','prior_rmse_pp','calibration_interval_min','status')},
        'purpose':'retrospective_model_review','status':'awaiting_review',
        'note':'04实测原值回传；同基准可查阅，须核对具体方案与方法。经验拟合与原始测量分列，未自动修订03模型。'
    })
