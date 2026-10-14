"""Compare freely estimated apparent plateau with the existing fixed-100% models."""
import runpy,json
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
ROOT=Path(__file__).resolve().parents[2]
ns=runpy.run_path(str(Path(__file__).with_name('fit.py')))
out=ns['out'];t=ns['t'];predict=ns['predict']
def fit_free(kind,x,y,upper=100):
 lower=[.1,.15,.1] if kind=='weibull' else [.0001,0,.1]
 hi=[1000,5,upper] if kind=='weibull' else [10,4.99,upper]
 starts=[[a,b,q] for a,b in ([[5,.5],[15,1],[30,2]] if kind=='weibull' else [[.05,0],[.1,2],[.2,4]]) for q in [85,99]]
 fun=lambda p:predict(kind,x,p[:2])*p[2]/100-y
 fits=[least_squares(fun,p,bounds=(lower,hi),max_nfev=5000,xtol=1e-12,ftol=1e-12,gtol=1e-12) for p in starts]
 best=min(fits,key=lambda r:sum(r.fun**2));p=best.x
 return {'params':p.tolist(),'fitted':(y+best.fun).tolist(),'residuals':best.fun.tolist(),'rmse':float(np.sqrt(np.mean(best.fun**2))),'converged':bool(best.success),'boundary':bool(np.any(np.isclose(p,lower,atol=1e-5)) or np.any(np.isclose(p,hi,atol=1e-5)))}
free={}
for kind in ['weibull','delay']:
 free[kind]={}
 for arm in ['low','high']:
  y=np.array(out['observations'][arm],float);result=fit_free(kind,t,y);loo=[];params=[];boundaries=[]
  for i in range(5):
   mask=np.arange(5)!=i;r=fit_free(kind,t[mask],y[mask]);p=r['params'];loo.append(float(predict(kind,t[i],p[:2])*p[2]/100));params.append(p);boundaries.append(r['boundary'])
  result.update(loo=loo,loo_params=params,loo_boundaries=boundaries,loo_rmse=float(np.sqrt(np.mean((np.array(loo)-y)**2))),loo_parameter_ranges=np.array([np.min(params,axis=0),np.max(params,axis=0)]).T.tolist(),upper120_sensitivity=fit_free(kind,t,y,120))
  free[kind][arm]=result
out['version']='tj-competition-v2';out['free_models']=free
out['plateau_note']='自由平台范围0.1–100%为事先约束，不以全数据最大观察值作下界。平台为该模型/条件的表观渐近值，不等于永久不可释放比例。附上界放宽120%的拟合敏感性检查。留出范围是删点敏感性，不是置信区间。'
(ROOT/'reference/tj0113-models/computed.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print('FREE PLATEAU SUMMARY')
for k in free:
 for a,r in free[k].items():print(k,a,'params',r['params'],'rmse',r['rmse'],'loo',r['loo_rmse'],'ranges',r['loo_parameter_ranges'],'loo boundary',r['loo_boundaries'])
