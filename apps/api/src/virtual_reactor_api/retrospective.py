"""Whole-formulation retrospective checks. No target labels enter fitting."""
import hashlib,json
import numpy as np

def features(rows,degree):
    x=np.array([(r['mcc_pct']-30)/5 for r in rows]);z=np.array([(r['starch_pct']-9.21)/2 for r in rows])
    return np.column_stack([np.ones(len(rows)),x,z]+([x*x,x*z,z*z] if degree==2 else []))

def predict(training,targets,degree):
    a=features(training,degree);y=np.array([r['q_pct'] for r in training])
    if np.linalg.matrix_rank(a)!=a.shape[1]:raise ValueError('设计矩阵不可辨识')
    coefficients=np.linalg.lstsq(a,y,rcond=None)[0]
    return features(targets,degree)@coefficients,coefficients,a

def paired_check(dataset):
    rows={r['id']:r for r in dataset['rows']}
    lo,mid,hi=[rows[x] for x in ('F1','F2','F5')]
    if len({r['mcc_pct'] for r in (lo,mid,hi)})!=1:raise ValueError('Pair MCC is not fixed')
    if max(r['starch_pct']+r['lactose_pct'] for r in (lo,mid,hi))-min(r['starch_pct']+r['lactose_pct'] for r in (lo,mid,hi))>1e-6:raise ValueError('Pair mass not conserved')
    weight=(mid['starch_pct']-lo['starch_pct'])/(hi['starch_pct']-lo['starch_pct'])
    predicted=[(1-weight)*a+weight*b for a,b in zip(lo['q_pct'],hi['q_pct'])]
    residual=[p-y for p,y in zip(predicted,mid['q_pct'])]
    contrasts=[]
    for lower,upper in [('F1','F5'),('F4','F6'),('F8','F3')]:
        a,b=rows[lower],rows[upper]
        contrasts.append({'from':lower,'to':upper,'mcc_pct':a['mcc_pct'],'starch_before_pct':a['starch_pct'],'starch_after_pct':b['starch_pct'],'delta_q_pp':[y-x for x,y in zip(a['q_pct'],b['q_pct'])]})
    return {'train_ids':['F1','F5'],'holdout_id':'F2','weight':weight,'predicted':predicted,'observed':mid['q_pct'],'residuals_pp':residual,'rmse_pp':float(np.sqrt(np.mean(np.array(residual)**2))),'max_error_pp':max(abs(x) for x in residual),'source_rows':[lo,mid,hi],'contrasts':contrasts,'formula':'w=(玉米淀粉%-6.38)/(12.04-6.38); Q(t)=(1-w)Q_F1(t)+w Q_F5(t). MCC固定30%，乳糖补差。','scope':'预先指定两个端点、完整中间处方留出；仅回顾性检验，不是独立批次验证。0–5分钟、30分钟后及6.38–12.04%之外不外推；17mg/90mg=18.89%超出本来源范围。'}

def execute(dataset):
    rows=dataset['rows'];target=next(r for r in rows if r['id']==dataset['holdout_id'])
    training=[r for r in rows if r['id']!=target['id']]
    # Intentionally discard target response before all prediction calls.
    target_x={k:v for k,v in target.items() if k!='q_pct'}
    results=[]
    raw=np.array([r['q_pct'] for r in rows])
    null_errors=np.array([np.delete(raw,i,axis=0).mean(axis=0)-raw[i] for i in range(len(rows))])
    null_rmse=float(np.sqrt(np.mean(null_errors**2)))
    for degree in (1,2):
        prediction,coef,a=predict(training,[target_x],degree)
        frozen={'train_ids':[r['id'] for r in training],'target':target_x,'coefficients':coef.tolist(),'predicted':prediction[0].tolist()}
        digest=hashlib.sha256(json.dumps(frozen,sort_keys=True).encode()).hexdigest()
        residual=prediction[0]-np.array(target['q_pct'])
        folds=[]
        for row in rows:
            others=[r for r in rows if r['id']!=row['id']]
            p,_,_=predict(others,[{k:v for k,v in row.items() if k!='q_pct'}],degree)
            err=p[0]-row['q_pct']
            folds.append({'id':row['id'],'predicted':p[0].tolist(),'observed':row['q_pct'],'rmse_pp':float(np.sqrt(np.mean(err**2)))})
        errors=np.array([np.array(f['predicted'])-f['observed'] for f in folds])
        results.append({'degree':degree,**frozen,'prediction_sha256':digest,'observed':target['q_pct'],'residuals_pp':residual.tolist(),'rmse_pp':float(np.sqrt(np.mean(residual**2))),'max_error_pp':float(max(abs(residual))),'condition_number':float(np.linalg.cond(a)),'folds':folds,'loo_rmse_pp':float(np.sqrt(np.mean(errors**2)))})
    for model in results:
        model['usable']=model['condition_number']<1000
        model['mean_reference_loo_rmse_pp']=null_rmse
        model['diagnostic']='设计条件数超过1000：留出唯一中心点后，二次项与截距近共线，舍入误差被放大；不展示为有效预测。1000是本次排错加入的工程保护阈值，不是统计检验。' if not model['usable'] else '输入设计可求解；仍需外部批次验证。'
    return {'paired_check':paired_check(dataset),'protocol':'retrospective-whole-formulation-v1','dataset':dataset,'models':results,'status':'completed','scope':'同研究回顾性整处方留出；不是盲法、独立批次验证或物理机理确证。模型比较预先固定为线性与二次，不按留出误差调参。','formula':'x=(MCC%-30)/5，z=(玉米淀粉%-9.21)/2；每个实测时间分别拟合 Q=b0+b1*x+b2*z（或加 b3*x²+b4*x*z+b5*z²）。乳糖按总比例补差。只在5–30分钟数据节点比较，不推算0–5分钟、平台或独立辅料贡献。'}

def load_case(root):
    path=root/'reference/mecobalamin-validation-20260925/dataset.json'
    return json.loads(path.read_text(encoding='utf-8'))

def register_calculation(store,pid,record,run_id=None):
    from .capsule_models import EvidenceInput
    for item in store.rows('evidence',pid):
        if item.get('fields',{}).get('retrospective_record_id')==record['id']:return item['id']
    return store.add_evidence(pid,EvidenceInput(section='comparison',title='整处方留出实际计算 '+record['id'],text=json.dumps(record,ensure_ascii=False),basis='hypothesis',access='imported',locator='retrospective_checks/'+record['id'],applicability='后台本轮计算，不是新实验或原文实测；含逐处方预测、误差及失败诊断。网页已有曲线和残差显示。',fields={'retrospective_record_id':record['id']}),run_id=run_id)['id']
