"""Source-only model comparison. LOO is time-point reconstruction, not transfer validation."""
from pathlib import Path
import json, hashlib
import numpy as np
from scipy.optimize import least_squares
ROOT=Path(__file__).resolve().parents[2]
raw=(ROOT/'reference/mcc-pgs-interactions-20260924/data.json').read_bytes()
s=json.loads(raw)['tj0113'];t=np.array(s['times_min'][:5],float)
def predict(kind,t,p):
 if kind=='weibull':return 100*(-np.expm1(-(t/p[0])**p[1]))
 return 100*(-np.expm1(-p[0]*np.maximum(t-p[1],0)))
def fit(kind,x,y):
 bounds=([.1,.15],[1000,5]) if kind=='weibull' else ([.0001,0],[10,4.99])
 starts=([5,.5],[15,1],[30,2]) if kind=='weibull' else ([.05,0],[.1,2],[.2,4])
 fits=[least_squares(lambda p:predict(kind,x,p)-y,p,bounds=bounds,xtol=1e-12,ftol=1e-12,gtol=1e-12) for p in starts]
 r=min(fits,key=lambda f:sum(f.fun*f.fun));p=r.x
 return p,{'params':p.tolist(),'fitted':predict(kind,x,p).tolist(),'residuals':r.fun.tolist(),'rmse':float(np.sqrt(np.mean(r.fun**2))),'boundary':bool(np.any(np.isclose(p,bounds[0],atol=1e-5)) or np.any(np.isclose(p,bounds[1],atol=1e-5))),'converged':bool(r.success)}
models={}
for kind in ['weibull','delay']:
 models[kind]={}
 for arm in ['low','high']:
  y=np.array(s[arm]['q'][:5],float);p,result=fit(kind,t,y);loo=[]
  for i in range(5):
   keep=np.arange(5)!=i;p1,_=fit(kind,t[keep],y[keep]);loo.append(float(predict(kind,t[i],p1)))
  result['loo']=loo;result['loo_rmse']=float(np.sqrt(np.mean((np.array(loo)-y)**2)));models[kind][arm]=result
out={'version':'tj-competition-v1','source_sha256':hashlib.sha256(raw).hexdigest(),'url':s['url'],'locator':s['locator'],'times':t.tolist(),'observations':{'low':s['low']['q'][:5],'high':s['high']['q'][:5]},'excluded':{'time_min':75,'reason':'60–75min升速250rpm，不进入恒条件拟合'},'models':models,'assumptions':['固定最终100%是建模假设，并非75rpm平台实测','每端每模型2参数，原始百分比空间等权最小二乘；中位数/RSD不转作均值/SD','Weibull tau几何插值、beta线性插值；延迟一阶k几何插值、lag线性插值，均未验证中间配比','5–60min显示；时间点逐一留出仅为重建敏感性检查，不是新配比或独立研究验证','未建立至诺氟沙星的迁移模型'],'bounds':{'weibull':{'tau_min':[.1,1000],'beta':[.15,5]},'delay':{'k_per_min':[.0001,10],'lag_min':[0,4.99]}}}
(ROOT/'reference/tj0113-models/computed.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(models,ensure_ascii=False,indent=2))
