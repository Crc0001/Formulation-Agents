"""Conditional source relations: empirical DOE and paired curves, never target facts."""
import hashlib
import json
import numpy as np

FOLDER = 'reference/mcc-pgs-interactions-20260924'

def terms(pgs, mcc):
    x, z = (pgs-10)/5, (mcc-35)/25
    return np.array([1, x, z, x*z, x*x, z*z], dtype=float)

def fit_response(s, key):
    X = np.array([terms(p,m) for p,m in zip(s['pgs_pct'],s['mcc_pct'])])
    y = np.array(s[key], dtype=float)
    if X.shape != (9,6) or not np.isfinite(y).all() or np.linalg.matrix_rank(X)!=6:
        raise ValueError('来源设计矩阵不完整')
    b = np.linalg.lstsq(X,y,rcond=None)[0]
    fitted = X@b
    # Whole-formulation leave-one-out; never use held-out DT to predict held-out Q.
    loo=[]
    for i in range(len(y)):
        keep=np.arange(len(y))!=i
        if np.linalg.matrix_rank(X[keep])!=6:raise ValueError('留出后设计秩不足')
        loo.append(float(X[i]@np.linalg.lstsq(X[keep],y[keep],rcond=None)[0]))
    c=s['confirmation']; pred=float(terms(c['pgs_pct'],c['mcc_pct'])@b)
    return {'coefficients':b.tolist(),'fitted':fitted.tolist(),'residuals':(y-fitted).tolist(),
        'rmse':float(np.sqrt(np.mean((y-fitted)**2))), 'loo_predictions':loo,
        'loo_rmse':float(np.sqrt(np.mean((y-np.array(loo))**2))),
        'confirmation_prediction':pred,'confirmation_observed':c[key],
        'confirmation_error':pred-c[key],
        'mixed_derivative':float(b[3]/125),
        'derivative_note':'混合偏导单位：响应单位/(PGS质量百分点×MCC质量百分点)；包含甘露醇补差效应'}

def source_relations(root):
    folder=root/FOLDER; path=folder/'data.json'
    if not path.is_file():return None
    d=json.loads(path.read_text(encoding='utf-8'))
    for key in ('sildenafil','tj0113','vildagliptin'):
        if key not in d:continue
        raw=folder/d[key]['file']
        if not raw.is_file():return None
        d[key]['sha256']=hashlib.sha256(raw.read_bytes()).hexdigest()
    s=d['sildenafil'];s['models']={k:fit_response(s,k) for k in ('q15','dt_s')}
    # Conditional simple effects are observed endpoint differences, not causal attribution.
    s['conditional_effects']=[{'mcc_pct':s['mcc_pct'][i],
        'delta_q15':s['q15'][i+6]-s['q15'][i],
        'delta_dt_s':s['dt_s'][i+6]-s['dt_s'][i]} for i in range(3)]
    t=d['tj0113']; width=t['high']['pgs_pct']-t['low']['pgs_pct']
    t['delta_q']=[b-a for a,b in zip(t['low']['q'],t['high']['q'])]
    t['secant_per_pgs_pp']=[x/width for x in t['delta_q']]
    if 'vildagliptin' in d:
        v=d['vildagliptin'];v['pairs']=[]
        for start,end in v['pair_runs']:
            i,j=v['runs'].index(start),v['runs'].index(end)
            v['pairs'].append({'from':start,'to':end,'ssg_pct':v['composition'][i][2],
                'pgs_before':v['composition'][i][3],'pgs_after':v['composition'][j][3],
                'delta_q10':v['q10'][j]-v['q10'][i],
                'delta_dt_s':v['dt_s'][j]-v['dt_s'][i],
                'delta_hardness_n':v['hardness_n'][j]-v['hardness_n'][i]})
    return d

def target_coordinates(base,variant):
    if not base or not variant or variant.get('baseline_id')!=base.get('id'):return None
    def coordinates(items):
        total=sum(x['amount_mg'] for x in items if x.get('role')!='shell')
        def amount(names):
            matches=[x for x in items if x['name'].strip().lower() in names]
            return 100*matches[0]['amount_mg']/total if len(matches)==1 and total>0 else None
        return {'pgs_pct':amount({'预胶化淀粉','部分预胶化淀粉','pregelatinized starch','partially pregelatinized starch'}),
                'mcc_pct':amount({'微晶纤维素','microcrystalline cellulose','mcc'})}
    before,after=coordinates(base['ingredients']),coordinates(variant['ingredients'])
    if any(v is None for v in [*before.values(),*after.values()]):return None
    return {'before':before,'after':after,'target_prediction_available':False,
        'note':'比例相同不等于体系相同；核对API负载、盐/晶型、牌号、工艺、润滑剂、介质。当前仅显示来源关系和目标坐标，不自动写入计算参数。'}

def register_sources(store,pid,rid,root):
    from .capsule_models import EvidenceInput
    d=source_relations(root)
    if not d:return {}
    ids={}
    for key in ('sildenafil','tj0113','vildagliptin'):
        if key not in d:continue
        s=d[key]
        existing=next((e for e in store.rows('evidence',pid) if e.get('fields',{}).get('mcc_pgs_source_sha256')==s['sha256']),None)
        if existing:ids[key]=existing['id'];continue
        raw={k:v for k,v in s.items() if k not in ('models','conditional_effects','delta_q','secant_per_pgs_pp','pairs')}
        ids[key]=store.add_evidence(pid,EvidenceInput(section='dissolution',title=s['title'],
            text=json.dumps(raw,ensure_ascii=False),basis='source',source_url=s['url'],access='imported',
            locator=s['locator'],applicability=s['conditions']+' '+s['limits'],
            fields={'mcc_pgs_source_sha256':s['sha256'],'verification':'人工核对PDF原表；结构化转录，非机器全文阅读声明'}),run_id=rid)['id']
    return ids
