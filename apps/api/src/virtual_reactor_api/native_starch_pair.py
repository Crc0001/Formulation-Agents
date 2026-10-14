"""Isolated paired-filler study. Source reconstruction is never target prediction."""
import json,math,hashlib
FOLDER='reference/lactose-native-starch-20260926'

def coordinates(base,variant):
    if not base or not variant or variant.get('baseline_id')!=base.get('id'):return None
    old={x['id']:x for x in base['ingredients']};new={x['id']:x for x in variant['ingredients']}
    if old.keys()!=new.keys():return None
    starch=[x for x in old.values() if x['name'] in ('特白玉米淀粉','玉米淀粉','原生玉米淀粉') and x.get('role')=='excipient']
    lactose=[x for x in old.values() if x['name'] in ('乳糖','一水乳糖','无水乳糖') and x.get('role')=='excipient']
    if len(starch)!=1 or len(lactose)!=1:return None
    a,b=starch[0]['id'],lactose[0]['id']
    for key,x in old.items():
        y=new[key]
        if key not in (a,b) and x!=y:return None
        if any(x.get(k)!=y.get(k) for k in ('name','role','brand','grade','particle')):return None
    vals=[old[a]['amount_mg'],old[b]['amount_mg'],new[a]['amount_mg'],new[b]['amount_mg']]
    if any(not math.isfinite(v) or v<=0 for v in vals):return None
    total=vals[0]+vals[1]
    if abs(total-vals[2]-vals[3])>1e-6 or vals[0]==vals[2]:return None
    return {'starch_before_mg':vals[0],'starch_after_mg':vals[2],'lactose_before_mg':vals[1],'lactose_after_mg':vals[3],'pair_total_mg':total,'x_before':100*vals[0]/total,'x_after':100*vals[2]/total,'coordinate':'starch % within lactose+starch, not % of whole tablet'}

def line(rows):
    xs=[r['starch_pair_pct'] for r in rows];ys=[math.log(r['k_min_inv']) for r in rows]
    mx=sum(xs)/len(xs);my=sum(ys)/len(ys);den=sum((x-mx)**2 for x in xs)
    if den<=0:raise ValueError('Distinct composition levels required')
    b=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/den
    return my-b*mx,b

def interpolate(rows,x):
    if not math.isfinite(x):raise ValueError('Finite coordinate required')
    rows=sorted(rows,key=lambda r:r['starch_pair_pct'])
    if not rows[0]['starch_pair_pct']<=x<=rows[-1]['starch_pair_pct']:raise ValueError('Outside source domain')
    for lo,hi in zip(rows,rows[1:]):
        if lo['starch_pair_pct']<=x<=hi['starch_pair_pct']:
            w=(x-lo['starch_pair_pct'])/(hi['starch_pair_pct']-lo['starch_pair_pct'])
            return math.exp((1-w)*math.log(lo['k_min_inv'])+w*math.log(hi['k_min_inv']))

def execute(root,base,variant,profiles):
    target=coordinates(base,variant)
    if not target:raise ValueError('Only an isolated equal-mass lactose/native-maize-starch swap is supported; other changes must be separated.')
    folder=root/FOLDER;data=json.loads((folder/'data.json').read_text(encoding='utf-8'))
    if hashlib.sha256((folder/'rizatriptan-full.html').read_bytes()).hexdigest()!=data['raw_sha256']:raise ValueError('Source changed; re-audit required')
    rows=data['rows'];a,b=line(rows);checks=[]
    for row in rows:
        training=[r for r in rows if r['id']!=row['id']];aa,bb=line(training)
        pred=math.exp(aa+bb*row['starch_pair_pct']);checks.append({'id':row['id'],'pred_k':pred,'observed_k':row['k_min_inv'],'error_pct':100*(pred/row['k_min_inv']-1),'domain':'interpolation' if min(r['starch_pair_pct'] for r in training)<row['starch_pair_pct']<max(r['starch_pair_pct'] for r in training) else 'extrapolation'})
    consistency=[{'id':r['id'],'calculated_t50':math.log(2)/r['k_min_inv'],'reported_t50':r['t50_min'],'difference_min':math.log(2)/r['k_min_inv']-r['t50_min']} for r in rows]
    curves=[{'name':r['id'],'kind':'author_parameter_reconstruction','points':[[t,100*(-math.expm1(-r['k_min_inv']*t))] for t in range(0,31)]} for r in rows]
    return {'version':data['version'],'baseline_id':base['id'],'variant_id':variant['id'],'source':data,'target':target,'source_curves':curves,'model':{'equation':'ln(k/min^-1)=a+b*x; x=starch % of filler pair','a':a,'b':b,'scope':'source empirical candidate, not mechanistic attribution'},'holdout':checks,'consistency':consistency,'target_curves':None,'baseline_profiles':[p for p in profiles if p['baseline_id']==base['id']],
    'stages':[{'name':'配对证据','status':'已取得4个共处理配比；非本品干混数据'},{'name':'来源复算','status':'已重建作者参数曲线；发现内部不一致'},{'name':'来源复验','status':'已做整配比留出；仅同研究参数检查，非原始曲线验证'},{'name':'目标迁移','status':'未通过：工艺/API/其他辅料不同，且来源冲突未解决'}],
    'next_actions':['核对原文图2与F7速率/半溶出时间矛盾；取得逐点数据后拟合自由平台模型。','寻找未共处理的原生玉米淀粉—乳糖干混直压配比梯度；分别归档粒度、压片和润滑条件。','目标乳糖43.3mg共筛/洗筛分配尚未确定；保留工艺未决项，不默认对半。'],
    'input_signature':hashlib.sha256(json.dumps({'base':base,'variant':variant,'source':data},sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
