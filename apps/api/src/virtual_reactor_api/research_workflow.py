"""Executed, immutable research checks. Narrative cannot certify execution."""
import hashlib,json,math
from .release_stages import fit_profile

def register_case_source(store,pid,rid,root):
    from xml.etree import ElementTree as ET
    from .capsule_models import EvidenceInput
    path=root/'reference/cross-formulation-validation-20260924/PMC8208916.xml'
    if not path.is_file():return None
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    for e in store.rows('evidence',pid):
        if e.get('fields',{}).get('workflow_source_sha256')==digest:return e['id']
    tree=ET.parse(path)
    body=tree.find('.//body')
    if body is None:raise ValueError('案例原文缺正文')
    return store.add_evidence(pid,EvidenceInput(section='dissolution',title='Steffens/Wagner2021：崩解剂用量及加入方式原始对照',
        text=' '.join(body.itertext()),basis='source',source_url='https://doi.org/10.1208/s12249-021-02056-0',
        locator='EuropePMC PMC8208916原始XML全文；表I–III、VII及Dissolution结果段',access='full_text',
        applicability='对乙酰氨基酚熔融制粒片剂；非诺氟沙星胶囊实测；CC BY4.0',
        fields={'workflow_source_sha256':digest}),run_id=rid)['id']

def execute_workflow(root,base,variant,profiles,include_method_example=False):
    from .mcc_pgs import source_relations,target_coordinates
    pair=source_relations(root);target=target_coordinates(base,variant)
    changes=[]
    old={i['id']:i for i in base['ingredients']}
    for item in variant['ingredients']:
        diff={k:{'before':old[item['id']].get(k),'after':item.get(k)} for k in ('amount_mg','brand','grade','particle') if old[item['id']].get(k)!=item.get(k)}
        if diff:changes.append({'name':item['name'],'fields':diff})
    fits=[];issues=[]
    for p in profiles:
        if p['baseline_id']!=base['id']:continue
        try:
            result=fit_profile(p)
            fits.append({'profile_id':p['id'],'medium':p['medium'],'source_url':p['source_url'],
                         'rmse_pp':result['best']['rmse_pp'],'converged':result['best']['converged'],
                         'residuals_pp':result['residuals_pp'],'trials':result['trials']})
        except ValueError as ex:issues.append({'profile_id':p['id'],'reason':str(ex)})
    case_path=root/'reference/cross-formulation-validation-20260924/results.json'
    xml=root/'reference/cross-formulation-validation-20260924/PMC8208916.xml'
    case=None;checks=[];challenge=None
    if include_method_example and not (target and pair) and case_path.is_file() and xml.is_file():
        case=json.loads(case_path.read_text(encoding='utf-8'))
        for key,r in case['records'].items():
            # Ignore saved predictions/parameters; recompute using ONLY endpoints.
            d0,dh,d1=[x/60 for x in r['dt_s']];q0,qh,q1=r['t80_min']
            if min(d0,dh,d1)<=0 or d0==d1:raise ValueError('来源崩解数据不支持此关系')
            b=(q1-q0)/(d1-d0);a=q0-b*d0
            pred_dt=math.sqrt(d0*d1);pred=a+b*pred_dt
            checks.append({'material':key,'grade':r['grade'],'train_doses_pct':[4,8],'holdout_dose_pct':6,
                'pred_dt_s':pred_dt*60,'observed_dt_s':dh*60,'pred_t80_min':pred,'observed_t80_min':qh,
                'error_min':pred-qh,'conditional_t80_min':a+b*dh,'a_min':a,'b':b})
        cpv=next(x for x in checks if x['material']=='CPV');raw=case['challenge']
        estimate=cpv['a_min']+cpv['b']*raw['dt_s']/60
        challenge={'sample':raw['sample'],'pred_t80_min':estimate,'observed_t80_min':raw['observed_t80_min'],'error_min':estimate-raw['observed_t80_min']}
    source_ok=bool((case or (target and pair)) and fits and not issues)
    # This adapter is explicitly a source-method demonstration, not a universal transfer engine.
    return {'mcc_pgs_relations':pair if target else None,'mcc_pgs_target':target,'version':'executed-workflow-v2','baseline_id':base['id'],'variant_id':variant['id'],
      'input_signature':hashlib.sha256(json.dumps({'base':base,'variant':variant,'profiles':profiles},sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
      'baseline_snapshot':base,'variant_snapshot':variant,'changes':changes,'source_fits':fits,'source_issues':issues,
      'case_source':{'url':case['source_url'],'raw_sha256':hashlib.sha256(xml.read_bytes()).hexdigest(),'data_sha256':hashlib.sha256(case_path.read_bytes()).hexdigest(),'identity':case['identity'],'method':case['method'],'composition_pct':case['composition_pct']} if case else None,
      'holdout_checks':checks,'challenge':challenge,'status':'partial','target_prediction_available':False,
      'steps':([
        {'name':'来源数据','status':'直接相关原表已取得','detail':'西地那非九处方及确认处方、TJ0113配对曲线；其它研究见条件关系库。'},
        {'name':'执行计算','status':'已执行','detail':'从原值重拟合Q15及DT二次响应面，计算同条件配对差；不读取旧拟合成功声明。'},
        {'name':'留出检查','status':'已执行，同研究复验','detail':'九次整处方留出及未参与估参的作者确认处方。'},
        {'name':'迁移判断','status':'待目标桥接','detail':'先核对组成域，再核对API、工艺、规格和检测条件；不把跨药来源模型当目标实测。'}
      ] if target and pair else [
        {'name':'来源数据','status':'已核对输入' if source_ok else '有缺口','detail':f'本基准可复算曲线{len(fits)}条；来源对照案例'+('已载入归档原文和数据。' if case else '未取得完整归档原文与数据。')},
        {'name':'执行计算','status':'已执行' if fits or checks else '未执行','detail':'由程序本轮重新计算；不是读取旧报告中的成功声明。'},
        {'name':'留出检查','status':'已执行，适用性有限' if checks else '缺来源数据','detail':'4/8%估参、6%留出仅为显式启用的方法示例。' if checks else '尚无与当前物料变化匹配的留出对照，不以其它崩解剂案例代替。'},
        {'name':'迁移判断','status':'暂不支持目标预测','detail':'围绕上述实际变化核对同物料的配对对照；来源曲线拟合不等于用量变化预测，不默认套用其它辅料模型。'}]),
      'next_action':'针对上述实际变化查找同物料、可比工艺的配对数据；共同约束崩散、吸液/湿态粒径及溶出。完整配方或独立批次留出复验。',
      'completion_note':'四步检查已执行不等于四步科学目标已达到；本版本无经过验证的目标迁移器。'}

def gate_report(report,workflow):
    report=dict(report or {})
    if workflow.get('mcc_pgs_relations'):
        prefix='【程序验收】本轮已从原值重新计算MCC—预胶化淀粉的Q15及崩解响应面、整处方留出、作者确认处方与配对差。记录 '+workflow['id']+'。\n'
    else:
        prefix='【程序验收】本轮后端重新计算了'+str(len(workflow['source_fits']))+'条基线及'+str(len(workflow['holdout_checks']))+'组留出对照；计算记录 '+workflow['id']+'。下文为模型解读，模型未调用计算工具不代表后端未执行。\n'
    report['summary']=prefix+report.get('summary','')
    report['gaps']=list(dict.fromkeys([*report.get('gaps',[]),
       '流程验收：本轮已保存实际计算与留出记录 '+workflow['id']+'；尚无适用于当前方案的已验证溶出迁移关系，保持部分完成。']))
    return report
