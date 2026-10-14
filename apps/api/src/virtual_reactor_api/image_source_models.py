"""Source-only modeling of archived image estimates; never raw-table or target data."""
import hashlib,json,math
from .source_curve_models import fit_curve

def predicted(t,m):
 p=m['parameters'];v=(max(t-p.get('lag_min',0),0)/p['tau_min']) if m['model']=='lag_first_order' else (t/p['tau_min'])**p['beta']
 return p['Qinf_percent']*(-math.expm1(-min(v,700)))

def fit_arm(arm):
 pts=arm['points'];xy=[[p['time_min'],p['q_percent']] for p in pts]
 if any(not math.isfinite(float(p[k])) or p[k]<0 for p in pts for k in ('time_min','q_percent','time_error_min','q_error_pp')):raise ValueError('估读值/误差非法')
 if any(p['q_error_pp']<=0 for p in pts):raise ValueError('估读数据必须带正误差范围')
 fitted=fit_curve(xy)
 perturb=[]
 for sign in (-1,1):
  perturb.append(fit_curve([[p['time_min'],max(0,p['q_percent']+sign*p['q_error_pp'])] for p in pts])['models'])
 for i,m in enumerate(fitted['models']):
  check=m['internal_last_point_check'];m['holdout_error_pp']=abs(check['predicted']-check['observed'])
  normalized=[abs(res)/max(p['q_error_pp'],.01) for res,p in zip(m['residuals_pp'],pts)]
  m['max_residual_error_ratio']=max(normalized)
  m['sensitivity_Qinf']=[min(x[i]['parameters']['Qinf_percent'] for x in perturb),max(x[i]['parameters']['Qinf_percent'] for x in perturb)]
  m['sensitivity_tau']=[min(x[i]['parameters']['tau_min'] for x in perturb),max(x[i]['parameters']['tau_min'] for x in perturb)]
  m['platform_at_upper_bound']=m['parameters']['Qinf_percent']>=m['bounds']['upper'][0]*.99
  stable=(m['sensitivity_tau'][1]/max(m['sensitivity_tau'][0],1e-8)<3 and m['sensitivity_Qinf'][1]-m['sensitivity_Qinf'][0]<20)
  m['eligible']=m['success'] and max(normalized)<=2 and m['holdout_error_pp']<=2*pts[-1]['q_error_pp'] and stable and not m['platform_at_upper_bound']
  m['selection_score']=m['rmse_pp']+m['holdout_error_pp']
  t0,t1=xy[0][0],xy[-1][0]
  m['curve']=[[t0+(t1-t0)*j/80,predicted(t0+(t1-t0)*j/80,m)] for j in range(81)]
 candidates=[m for m in fitted['models'] if m['eligible']]
 best=min(candidates,key=lambda m:m['selection_score']) if candidates else None
 return dict(label=arm['label'],legend_identity=arm['legend_identity'],points=pts,models=fitted['models'],selected_model=best['model'] if best else None,decision='推荐来源描述模型：'+best['model'] if best else '两种单调模型均未通过当前工程筛查，保留估读点，不强行选模',observed_last_percent=pts[-1]['q_percent'])

def comparisons(arms):
 result=[]
 for i,a in enumerate(arms):
  for b in arms[i+1:]:
   points=[]
   for p in a['points']:
    matches=[q for q in b['points'] if abs(q['time_min']-p['time_min'])<=p['time_error_min']+q['time_error_min']]
    if len(matches)!=1:continue
    q=matches[0];delta=q['q_percent']-p['q_percent'];err=q['q_error_pp']+p['q_error_pp']
    points.append(dict(time_a=p['time_min'],time_b=q['time_min'],delta_pp=delta,reading_margin_pp=err,direction='暂不能区分' if abs(delta)<=err else ('B较高' if delta>0 else 'B较低')))
   result.append(dict(a=a['label'],b=b['label'],points=points,note='按时间估读区间重叠配对，不代表精确同一时刻；差值与两侧读图误差和比较，不是统计检验。小时间偏差的动力学影响未消除。'))
 return result

def build(evidence,ids,root):
 refs={e['id']:e for e in evidence};inputs=[];arms=[]
 if not 2<=len(set(ids))<=8 or len(set(ids))!=len(ids):raise ValueError('选择2–8个不同的同源图像估读记录')
 for eid in ids:
  e=refs.get(eid)
  if not e or e.get('basis')!='image_estimate':raise ValueError('仅接受本项目图中估读记录')
  d=json.loads(e.get('fields',{}).get('digitized_chart_json','null'))
  if not d or d.get('version')!='chart-pixels-v1':raise ValueError('不是已执行的坐标提取记录')
  sha=d.get('sha256','')
  import re
  if not re.fullmatch('[a-f0-9]{64}',sha):raise ValueError('归档图像摘要非法')
  path=root/'data/documents'/sha
  if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError('原图缺失或变更')
  from .chart_digitization import Geometry,convert
  checked=convert(Geometry.model_validate(d['geometry']),d['width'],d['height'])
  if len(checked['arms'])!=len(d['arms']):raise ValueError('保存曲线与像素复算不一致')
  for a,b in zip(checked['arms'],d['arms']):
   if a['label']!=b['label'] or len(a['points'])!=len(b['points']):raise ValueError('保存图例/点数与像素复算不一致')
   for p,q in zip(a['points'],b['points']):
    if any(abs(p[k]-q[k])>1e-6 for k in ('time_min','q_percent','time_error_min','q_error_pp')):raise ValueError('估读数值与归档像素复算不一致')
  inputs.append(dict(evidence_id=eid,source=d))
  for a in d['arms']:arms.append({**fit_arm(a),'source_id':eid,'panel':d['panel']})
 if len({v['source']['sha256'] for v in inputs})!=1:raise ValueError('当前入口仅比较同一归档图的子图；不同论文条件不能自动合并')
 key=hashlib.sha256(json.dumps(inputs,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 return dict(version='image-source-model-v1',input_hash=key,inputs=inputs,arms=arms,comparisons=comparisons(arms),target_prediction=None,
 selection_rule='拟合残差≤2倍逐点估读范围，末点内部留出误差≤2倍末点估读范围；上下估读边界扰动的tau比<3、Qinf跨度<20百分点、平台不触上界。通过者按RMSE+末点误差择优。这是工程筛查，非统计验证。',
 limits=['原图哈希和坐标结构检查不等于人工确认图例/样品/条件。','平台是自由拟合参数，不固定100%；没有后续时间数据不能确认真实终点。','敏感性仅为全部纵坐标同时上下移动估读范围的两种情景，不是完整不确定性传播或置信区间。时间估读误差未进入拟合，仅列出供审查。','估读数据与原始表值隔离，末点留出不是独立实验验证。','本模型只描述来源曲线；乳糖逐批量及补差映射未确认，不赋予甲钴胺预测或独立辅料贡献。'])
