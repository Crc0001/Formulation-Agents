from .table_vision import usable_source, source_notice
"""Agent-callable source reproduction; never fabricates target curves."""
import json,math,re
import numpy as np
from scipy.optimize import least_squares
from .capsule_models import EvidenceInput
from .source_metrics import source_numbers

def dissolution_numbers(text):
    # Accept adjacent explicit units, but not arbitrary identifiers (F5, CN123).
    normalized=re.sub(r'(?<=\d)(?:minutes?|mins?|min|分钟|分|％|%)(?![A-Za-z0-9_])',' ',text,flags=re.I)
    return source_numbers(normalized)

def point_quote_numbers(point, text):
    compact=lambda s:re.sub(r'\s+','',s)
    quote=point.get('quote','')
    if len(quote)<8 or compact(quote) not in compact(text):raise ValueError('逐点摘录未在原文找到')
    header=point.get('time_quote')
    if header is None:return dissolution_numbers(quote),dissolution_numbers(quote)
    if not point.get('time_locator') or not point.get('value_locator'):raise ValueError('分离表头与样品行须分别提供定位')
    if len(header)<8 or compact(header) not in compact(text):raise ValueError('时间表头摘录未在同一原文找到')
    # Interpret only explicit unit-dash column formatting, not arbitrary negatives.
    header=re.sub(r'\b(minutes?|mins?|min)\s*[-–—]\s*(?=\d)',r'\1 ',header,flags=re.I)
    return dissolution_numbers(header),dissolution_numbers(quote)

def fit_curve(points):
    a=np.asarray(points,dtype=float)
    if a.ndim!=2 or a.shape[1]!=2 or not 6<=len(a)<=100 or not np.isfinite(a).all():raise ValueError('每臂须6–100个逐点值，含至少5个正时间点；不补造时间零点')
    t,y=a.T
    if np.any(np.diff(t)<=0) or np.any(t<0) or np.any(y<0) or np.count_nonzero(t>0)<5:raise ValueError('时间须递增非负，响应非负；原值不裁剪')
    ceiling=max(120.,float(max(y))*1.5)
    def calc(tt,p,kind):
        if kind=='weibull':return p[0]*(-np.expm1(-np.power(tt/p[1],p[2])))
        return p[0]*(-np.expm1(-np.maximum(tt-p[2],0)/p[1]))
    def fit(tt,yy,kind):
        lower=[.001,.0001,.1 if kind=='weibull' else 0]
        upper=[ceiling,max(t)*100,5 if kind=='weibull' else max(t)*.95]
        starts=[[min(max(yy),ceiling*.99),max(float(np.median(tt)),.001),b] for b in ([.5,1,2] if kind=='weibull' else [0,float(t[1])*.5])]
        fits=[least_squares(lambda p:calc(tt,p,kind)-yy,x,bounds=(lower,upper),max_nfev=1500) for x in starts]
        f=min(fits,key=lambda f:float(np.sum(f.fun**2)))
        return f,lower,upper
    models=[]
    for kind in ['lag_first_order','weibull']:
        f,lo,hi=fit(t,y,kind);pred=calc(t,f.x,kind);held,_,_=fit(t[:-1],y[:-1],kind)
        models.append({'model':kind,'parameters':dict(zip(['Qinf_percent','tau_min','beta' if kind=='weibull' else 'lag_min'],map(float,f.x))),
          'bounds':{'lower':lo,'upper':hi},'success':bool(f.success),'boundary':any(abs(v-l)<1e-4 or abs(v-h)<1e-4 for v,l,h in zip(f.x,lo,hi)),
          'rmse_pp':float(np.sqrt(np.mean((pred-y)**2))),'residuals_pp':(pred-y).tolist(),'fitted_points':np.column_stack([t,pred]).tolist(),
          'internal_last_point_check':{'time_min':float(t[-1]),'observed':float(y[-1]),'predicted':float(calc(t[-1:],held.x,kind)[0]),'identity':'前面点拟合、最后点内部留出；非独立批验证'}})
    return {'observed_points':a.tolist(),'models':models}

def paired_relation(arms):
    left={float(t):float(q) for t,q in arms[0]['observed_points']}
    right={float(t):float(q) for t,q in arms[1]['observed_points']}
    times=sorted(set(left)&set(right))
    rows=[{'time_min':t,'before_percent':left[t],'after_percent':right[t],'delta_pp':right[t]-left[t]} for t in times]
    signs={1 if x['delta_pp']>0 else -1 for x in rows if x['delta_pp']!=0}
    direction='mixed' if len(signs)>1 else 'increase' if signs=={1} else 'decrease' if signs=={-1} else 'equal' if rows else 'unknown'
    return {'matched_time_differences':rows,'observed_direction':direction,'identity':'来源两臂在共同实测时间的差值；不插值，不代表独立辅料效应或目标预测','uncertainty':'未输入逐杯重复性，未判断统计显著性；符号变化不证明真实动力学交叉'}

def calculate_and_save(store,pid,run_id,data):
    if store.run(run_id)['project_id']!=pid:raise ValueError('运行项目不匹配')
    evidence={e['id']:e for e in store.rows('evidence',pid)}
    if len(data.get('arms',[]))!=2:raise ValueError('须恰好两臂原始来源对照')
    for k in ['title','conditions','change','confounders']:
        if not str(data.get(k,'')).strip():raise ValueError('缺少'+k)
    results=[];ids=[]
    compact=lambda s:re.sub(r'\s+','',s)
    for arm in data['arms']:
        e=evidence.get(arm.get('source_id'))
        if not usable_source(e,list(evidence.values())):raise ValueError('须绑定本项目已读取原文，不用摘要/假设')
        if not arm.get('label') or not arm.get('locator'):raise ValueError('缺少样品身份或原文定位')
        points=[]
        for point_index,p in enumerate(arm['points'],1):
            times,values=point_quote_numbers(p,e['text'])
            if p['time_min'] not in times or p['q_percent'] not in values:raise ValueError(f"{arm['label']}第{point_index}点：时间或响应未在相应原文摘录中识别；核对表头和样品行")
            points.append([p['time_min'],p['q_percent']])
        # Sparse sources still yield an observed paired relationship, not invented fit points.
        if len(points)<2 or any(not all(math.isfinite(v) and v>=0 for v in p) for p in points) or any(points[i][0]>=points[i+1][0] for i in range(len(points)-1)):
            raise ValueError('至少2个有限非负原始点，时间递增')
        fitted=fit_curve(points) if len(points)>=6 and sum(p[0]>0 for p in points)>=5 else {'observed_points':points,'models':[],'fit_gap':'原始点不足以进行当前三参数模型及内部留出；保留实测对照，不补造点'}
        results.append({**{k:arm[k] for k in ['label','source_id','locator']},'point_evidence':arm['points'],**fitted});ids.append(e['id'])
    result={'model_id':'source-dissolution-comparison-v1','run_id':run_id,**{k:data[k] for k in ['title','conditions','change','confounders']},'arms':results,'paired_relation':paired_relation(results),'target_prediction':None,
      'limitations':['仅来源曲线复现，不自动估计当前处方或辅料独立贡献。','摘录核对不能自动证明表格行列、样品及控制条件一致，仍须原文审查。','参数上下界为数值约束，平台未被末端数据识别时不得认定真实终点；拟合优度不是物理正确性。','最后点检查为内部时间留出，不能视为独立实验验证。']}
    result['source_readings']=[source_notice(evidence[sid],list(evidence.values())) for sid in ids]
    result['limitations'].extend(dict.fromkeys(result['source_readings']))
    saved=store.add_evidence(pid,EvidenceInput(section='comparison',title=data['title'],basis='hypothesis',access='imported',text='程序执行两种来源溶出模型拟合与内部留出检查；非目标预测。',applicability='；'.join(result['limitations']),fields={'source_curve_model_json':json.dumps(result,ensure_ascii=False,allow_nan=False),'source_ids_json':json.dumps(ids)}),run_id)
    return {'evidence_id':saved['id'],'result':result}
