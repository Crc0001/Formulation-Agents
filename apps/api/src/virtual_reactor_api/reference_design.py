"""Retrospective two-factor reference matching; no regulatory similarity claim."""
import numpy as np

def analyze(data, reference_id):
    members=[r for r in data['references'] if r.get('group')==reference_id]
    ref=({'id':reference_id,'label':members[0]['medium']+' / 全部参比批次','q':np.mean([r['q'] for r in members],axis=0).tolist(),'method':members[0]['method'],'locator':members[0]['locator']} if members else next((r for r in data['references'] if r['id']==reference_id),None))
    if ref is None: raise ValueError('请选择一个有明确批次及方法的参比')
    trials=data['trials'];x=np.array([t['factors'] for t in trials],float); y=np.array([t['q'] for t in trials],float);target=np.array(ref['q'],float)
    if x.shape!=(len(trials),2) or y.shape!=(len(trials),len(data['times'])) or target.shape!=(y.shape[1],) or len(trials)<8:raise ValueError('需至少8组双因素及同时间点数据')
    if not all(np.isfinite(v).all() for v in (x,y,target)):raise ValueError('数据必须为有限数值')
    levels=[np.unique(x[:,j]) for j in range(2)]
    if any(len(a)<3 for a in levels) or len(set(map(tuple,x)))!=len(x) or len(x)!=len(levels[0])*len(levels[1]):raise ValueError('本求解器要求完整的双因素交叉设计，每因素至少3水平')
    center=(x.max(0)+x.min(0))/2;scale=(x.max(0)-x.min(0))/2;z=(x-center)/scale
    def design(a,kind):
        base=[np.ones(len(a)),a[:,0],a[:,1],a[:,0]*a[:,1]]
        if kind=='quadratic':base += [a[:,0]**2,a[:,1]**2]
        return np.array(base).T
    fits=[]
    for kind in ['interaction','quadratic']:
        a=design(z,kind)
        if np.linalg.matrix_rank(a)<a.shape[1]:continue
        coeff=np.linalg.lstsq(a,y,rcond=None)[0];res=a@coeff-y;held=[]
        for i in range(len(x)):
            keep=np.arange(len(x))!=i
            if np.linalg.matrix_rank(a[keep])<a.shape[1]:break
            held.append(a[i]@np.linalg.lstsq(a[keep],y[keep],rcond=None)[0]-y[i])
        if len(held)!=len(x):continue
        fits.append({'kind':kind,'coefficients':coeff.tolist(),'rmse':float(np.sqrt(np.mean(res**2))),'loo_rmse':float(np.sqrt(np.mean(np.array(held)**2)))})
    if not fits:raise ValueError('设计无法识别候选模型')
    reference_values=np.array([r['q'] for r in members] if members else [target],float)
    def distance(q):return np.sqrt(np.mean((np.asarray(q)[...,None,:]-reference_values)**2,axis=-1)).max(axis=-1)
    best=min(fits,key=lambda m:m['loo_rmse']); grid=np.array([[a,b] for a in np.linspace(*[x[:,0].min(),x[:,0].max()],61) for b in np.linspace(x[:,1].min(),x[:,1].max(),61)])
    pred=design((grid-center)/scale,best['kind'])@np.array(best['coefficients']);err=distance(pred);i=int(np.argmin(err))
    ranked=sorted([{'batch':t['batch'],'factors':t['factors'],'q':t['q'],'rmse_to_reference':float(distance(y[k]))} for k,t in enumerate(trials)],key=lambda r:r['rmse_to_reference'])
    delta=np.array(ranked[0]['q'])-target
    gain=ranked[0]['rmse_to_reference']-float(err[i])
    predictions=[design((grid-center)/scale,m['kind'])@np.array(m['coefficients']) for m in fits]
    disagreement=np.ptp(np.array(predictions),axis=0).max(axis=1)
    unsampled=np.array([not np.any(np.all(np.isclose(x,g),axis=1)) for g in grid])
    j=int(np.argmax(np.where(unsampled,disagreement,-1)))
    guidance={'goal':'以参比各批次为共同目标；先缩小释放偏差，再验证处方和工艺的稳健性。',
      'observed_best':ranked[0]['batch'],'deviations':[{'time':t,'difference':float(v),'direction':'高于参比均值' if v>0 else '低于参比均值' if v<0 else '与参比均值相同'} for t,v in zip(data['times'],delta)],
      'expected_gain':gain,'caution':'模型拟合推荐改善幅度不大于内部留出误差，优先复验而非直接认定新配比更好。' if gain<=best['loo_rmse'] else '模型改善值得验证，但内部误差不是置信区间，尚未独立确认。',
      'next_experiments':[{'purpose':'复验实测最接近组，建立重复性锚点','factors':ranked[0]['factors']}, {'purpose':'验证模型优选配比是否比实测最接近组更接近参比','factors':grid[i].tolist()}, {'purpose':'两种模型分歧最大的未测配比，用于辨别曲率与交互假设','factors':grid[j].tolist(),'model_disagreement_pp':float(disagreement[j])}],
      'execution':'仅为候选试验建议；同介质同方法、原料规格、工艺与MCC补差须记录，不自动执行或采用。'}
    return {'reference':ref,'reference_members':members or [ref],'guidance':guidance,'times':data['times'],'factor_names':data['factor_names'],'unit':data['unit'],'models':fits,'selected':best,'center':center.tolist(),'scale':scale.tolist(),'observed_ranking':ranked,'candidate':{'factors':grid[i].tolist(),'q':pred[i].tolist(),'rmse_to_reference':float(err[i])},'comparability':data['comparability'],'status':'条件情景，待核方法，不能确认最佳处方' if data['comparability']!='confirmed' else '回顾性优选候选，待独立确认','constraints':data['constraints'],'source':data['source'],'objective':'共同时间点对各参比批次分别计算RMSE，以最差批次偏差最小进行排序；单位为百分点。均值仅用于绘图，不作为合格限度；不是法规f2或等效性结论','grid_step':((x.max(0)-x.min(0))/60).tolist(),'validation':'留一处方内部检验，非独立实验验证'}
