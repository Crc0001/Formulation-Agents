"""Conservative serial-release hypothesis. Rate labels are NOT identifiable from Q alone."""
import math
import numpy as np
from scipy.linalg import expm
from scipy.optimize import least_squares

def states(times,rates):
    if len(rates)!=3 or any(not math.isfinite(k) or k<=0 for k in rates):raise ValueError('三阶段速率须为有限正数')
    if any(not math.isfinite(t) or t<0 for t in times):raise ValueError('时间须非负有限')
    a,b,c=rates
    matrix=np.array([[-a,0,0,0],[a,-b,0,0],[0,b,-c,0],[0,0,c,0]],dtype=float)
    return np.array([expm(matrix*t)[:,0]*100 for t in times])

def fit_profile(profile):
    points=profile['points'];ts=np.array([p[0] for p in points]);ys=np.array([p[1] for p in points])
    if len(points)<4 or len(set(ts))<4:raise ValueError('至少4个不同时间点才能进行三阶段探索')
    starts=[[.03,.1,.3],[.3,.03,.1],[.1,.3,.03],[.1,.1,.1]]
    trials=[]
    for start in starts:
        out=least_squares(lambda logs:states(ts,np.exp(logs))[:,3]-ys,np.log(start),bounds=(np.log(.001),np.log(10)),max_nfev=160)
        rates=np.exp(out.x);pred=states(ts,rates)[:,3]
        trials.append({'rates_per_min':rates.tolist(),'rmse_pp':float(np.sqrt(np.mean((pred-ys)**2))),'converged':bool(out.success)})
    best=min(trials,key=lambda x:x['rmse_pp']);rates=best['rates_per_min'];grid=np.linspace(0,max(ts),91).tolist()
    fitted=states(ts,rates)[:,3]
    scenarios=[]
    for i,name in enumerate(['胶囊开启/内容物崩散','颗粒润湿/暴露','有效溶解']):
        for multiplier in (.5,2):
            changed=list(rates);changed[i]*=multiplier
            scenarios.append({'stage':name,'multiplier':multiplier,'percent':states(grid,changed)[:,3].tolist()})
    return {'model_id':'serial-release-hypothesis-v1','profile_id':profile['id'],'baseline_id':profile['baseline_id'],
      'input_profile':profile,'trials':trials,'best':best,'times_min':grid,'states_percent':states(grid,rates).tolist(),
      'fitted_at_observations':fitted.tolist(),'residuals_pp':(ys-fitted).tolist(),'scenarios':scenarios,
      'permutation_difference_pp':float(np.max(np.abs(states(ts,rates)[:,3]-states(ts,rates[::-1])[:,3]))),
      'status':'来源曲线校准；三阶段归属不可辨识，不能作为辅料贡献或调整预测',
      'assumptions':['初始100%在未释放状态；各阶段常速率、不可逆，最终可释放100%。未单设囊壳延迟。',
        '四次不同初值拟合是数值复验，不是四次实验或独立验证。',
        '速率顺序交换产生同一总释放曲线；最优参数不能自动命名为某辅料的作用。',
        '0.5/2倍是显式敏感性假设，不是辅料用量倍数或置信区间。',
        '未纳入动态膨胀、团聚、有限溶解容量或粒径分布；系统残差提示模型需要扩展。'],
      'equations':['dU/dt=-kb U','dG/dt=kb U-kw G','dW/dt=kw G-kd W','dQ/dt=kd W','U+G+W+Q=100'],
      'next_measurements':['同条件囊壳开启与内容物崩散时间序列，约束kb；不能单归因于崩解剂。','颗粒吸液、润湿后粒径/团聚与有效暴露面积，约束kw；关注润滑历史。','相同介质API溶解度、PSD与独立溶解数据，约束kd；非漏槽须改用容量耦合模型。']}
