"""Retrospective formulation-level check; not independent experimental validation.
Source: Steffens & Wagner 2021, DOI 10.1208/s12249-021-02056-0,
CC BY 4.0. Original full text is archived next to this script.
Adaptation: selected source means/SDs and our explicitly empirical calculations.
"""
import json, math
from pathlib import Path

root=Path(__file__).resolve().parents[2]
records={
 'CPV':{'name':'交联聚维酮','grade':'Kollidon CL-F','dt_s':[211,129,78],'dt_sd_s':[27,29,7],'t80_min':[7.0,5.2,4.2],'t80_sd_min':[1.3,1.0,.4]},
 'CCS':{'name':'交联羧甲纤维素钠','grade':'Vivasol GF','dt_s':[435,360,390],'dt_sd_s':[69,88,93],'t80_min':[17,15.2,11],'t80_sd_min':[2.4,3.7,0]},
 'SSG':{'name':'羧甲淀粉钠','grade':'Vivastar P','dt_s':[598,492,513],'dt_sd_s':[37,67,38],'t80_min':[32.8,17.7,14.7],'t80_sd_min':[6.5,3.7,.8]},
}
for r in records.values():
 d0,dh,d1=[x/60 for x in r['dt_s']];q0,qh,q1=r['t80_min']
 # Fit ONLY 4% and 8%. Dose c is numerical weight percent, not fraction.
 beta=math.log(d1/d0)/4;alpha=math.log(d0)-4*beta
 slope=(q1-q0)/(d1-d0);intercept=q0-slope*d0
 dp=math.exp(alpha+beta*6);qp=intercept+slope*dp
 conditional=intercept+slope*dh
 r.update(parameters={'alpha':alpha,'beta_per_weight_pp':beta,'a_min':intercept,'b':slope},
   holdout={'dose_pct':6,'pred_dt_s':dp*60,'observed_dt_s':dh*60,'pred_t80_min':qp,
     'observed_t80_min':qh,'error_min':qp-qh,'conditional_t80_from_measured_dt':conditional,
     'conditional_error_min':conditional-qh})

p=records['CPV']['parameters'];challenge=p['a_min']+p['b']*957/60
result={'source_url':'https://doi.org/10.1208/s12249-021-02056-0','pmcid':'PMC8208916',
 'identity':'对乙酰氨基酚500mg片剂；双螺杆熔融制粒；150MPa压片、13mm冲模、停留6–7ms；PEG6000黏合；MgSt 1%；外加崩解剂4/6/8%。',
 'method':'溶出：900mL pH5.8磷酸盐，桨法50rpm，37±0.5℃，n=6。崩解：800mL去离子水，37±1℃，n=6。两项检测介质不同。',
 'composition_pct':{'4':{'PCM':84.55,'PEG6000':9.5,'silica':.95,'MgSt':1,'disintegrant':4},'6':{'PCM':82.77,'PEG6000':9.3,'silica':.93,'MgSt':1,'disintegrant':6},'8':{'PCM':80.99,'PEG6000':9.1,'silica':.91,'MgSt':1,'disintegrant':8}},
 'equations':['ln(DT/min)=alpha+beta*c','t80/min=a+b*(DT/min)'],
 'split':'4%和8%估参，6%整处方留出；已阅读全部资料后的回顾性检查，不是盲测、跨研究验证或独立批次验证。',
 'records':records,'challenge':{'sample':'CPV总量6%，全部内加','dt_s':957,'dt_sd_s':97,'observed_t80_min':101,'sd_min':9.8,'pred_t80_min':challenge,'error_min':challenge-101,'status':'外加工艺关系外推失败；该点未用于估参'},
 'limitations':['两点确定一条关系，训练误差为零无验证意义。','只验证崩解时间与t80终点关系，未复验三阶段完整曲线，不由t80反造曲线。','增加崩解剂伴随API及其他组分比例变化、片重变化，不能归为纯独立贡献。','不同用量/加入方式会改变孔隙和强度；固定润湿与溶解阶段的假设未被证明。','来源SD保留为实验离散度，不当作预测区间；不设任意误差合格线。','不能将对乙酰氨基酚片剂系数直接用于诺氟沙星干法制粒胶囊。']}
out=root/'apps/web/src/known-release-validation.json'
out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
Path(__file__).with_name('results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
for key,r in records.items():print(key,json.dumps(r['holdout'],ensure_ascii=False))
print('challenge',json.dumps(result['challenge'],ensure_ascii=False))
