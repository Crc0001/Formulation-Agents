"""Agent 02 inventory and agent 03 constrained candidate planning."""
import itertools,math
from collections import Counter
from pydantic import BaseModel,Field

ORGANIZE_MARKER='【角色：选定处方的辅料整理】'
ORGANIZE_POLICY='''你是02辅料实验及文献数据智能体，只负责信息收集、原文数据提取、比较研究准备。不执行配方模拟、参数拟合或DoE，不要求用户先调整配方。依据冻结基准及本轮目录范围逐一整理辅料：实际用量/加入方式、功能及条件、厂家牌号粒度、关键物性与缺口；列出本轮目录范围内所有两两配对，区分等量补差研究与相互作用研究，不默认任何一对可替换。只建立资料目录与优先研究线索，不代替03进行专项机制建模；把建议研究目标和现有原文定位交给03。输出excipient_organization，材料ingredient_id和配对left_id/right_id必须取自冻结基准。每条给出原文source_ids、性质/响应/工艺/范围或具体缺口；无法取得数据仍逐项列出，不填通用作用系数。材料和配对research_notes写可供03建模的数据位置、单位、控制条件、适用性及待补字段。交付仅为研究包，不是处方采纳或已验证预测。最终保存阶段稿，明确下一项补查。不要求substitution_assessment或screening_progress，不强行作目标变化预测。'''

class MaterialReview(BaseModel):
    ingredient_id:str
    functional_features:str
    brand_grade_options:str
    research_notes:str
    source_ids:list[str]=Field(default_factory=list)
    gaps:list[str]=Field(default_factory=list)
class PairReview(BaseModel):
    left_id:str
    right_id:str
    relationship:str
    research_notes:str
    source_ids:list[str]=Field(default_factory=list)
    gaps:list[str]=Field(default_factory=list)
class OrganizationReport(BaseModel):
    materials:list[MaterialReview]=Field(default_factory=list)
    pairs:list[PairReview]=Field(default_factory=list)
    next_research:list[str]=Field(default_factory=list)

def inventory(base,include_coating=False):
    materials=[x for x in base['ingredients'] if x['role']=='excipient' or (include_coating and x['role']=='shell')]
    return {'baseline_id':base['id'],'materials':materials,'pairs':[{'left_id':a['id'],'right_id':b['id'],'left_name':a['name'],'right_name':b['name'],'status':'待研究；不代表允许互换'} for a,b in itertools.combinations(materials,2)]}

def citation_corrections(evidence):
    sources={e['id']:e for e in evidence};result=[]
    for e in evidence:
        f=e.get('fields',{});old=f.get('citation_alias_from');target=sources.get(f.get('citation_alias_to'));quote=f.get('citation_source_quote','')
        if old and old not in sources and target and len(quote)>=12 and quote in target.get('text','') and target.get('basis')=='source' and target.get('access') in ('full_text','page_text'):
            result.append({'from':old,'to':target['id'],'title':target['title'],'correction_id':e['id']})
    return result

def audit_organization(report,base,evidence,include_coating=False):
    expected=inventory(base,include_coating);ids={x['id'] for x in expected['materials']};pairs={frozenset((x['left_id'],x['right_id'])) for x in expected['pairs']}
    if not report:return ['尚未交付全方辅料研究包']
    r=OrganizationReport.model_validate(report);issues=[]
    mids=[m.ingredient_id for m in r.materials];pids=[frozenset((p.left_id,p.right_id)) for p in r.pairs]
    if set(mids)!=ids or len(mids)!=len(set(mids)):issues.append('辅料目录存在缺项、重复或非基准物料')
    if set(pids)!=pairs or len(pids)!=len(set(pids)):issues.append('两两配对目录存在缺项、重复或非基准配对')
    sources={e['id']:e for e in evidence}
    for e in evidence:
        digest=e.get('fields',{}).get('verified_workbook_sha256')
        if digest and e.get('access')=='imported':sources[digest]=e
    for correction in citation_corrections(evidence):sources[correction['from']]=sources[correction['to']]
    for item in [*r.materials,*r.pairs]:
        if not item.source_ids and not item.gaps:issues.append('无来源条目必须列出具体缺口')
        for sid in item.source_ids:
            if sid not in sources or sources[sid].get('access') not in ('full_text','page_text','imported','user'):
                label=item.ingredient_id if isinstance(item,MaterialReview) else item.left_id+'/'+item.right_id
                issues.append(f'{label}：引用未绑定可读原文：{sid}')
    return list(dict.fromkeys(issues))

def activity_summary(events):
    counts=Counter(e['kind'] for e in events)
    return {'search_requests':counts['search_request'],'document_requests':counts['document_request'],
            'search_errors':counts['search_error'],'document_errors':counts['document_error'],
            'summary':f"本轮实际发起{counts['search_request']}次搜索、{counts['document_request']}次原文读取请求；搜索失败{counts['search_error']}次、原文读取失败{counts['document_error']}次（请求次数不代表成功取得来源数）"}

def organization_review(run,base,evidence,events,include_coating=False):
    """Read-only review: retain historical reports and distinguish coverage from science."""
    report=run.get('report') or {};packet=report.get('excipient_organization') or {}
    expected=inventory(base,include_coating);issues=audit_organization(packet or None,base,evidence,include_coating)
    legacy={'未交付候选筛选卡，本轮筛选未完成。','未交付替换对照分析','未交付候选筛选卡'}
    return {'materials':len(packet.get('materials',[])),'expected_materials':len(expected['materials']),
            'pairs':len(packet.get('pairs',[])),'expected_pairs':len(expected['pairs']),
            'issues':issues,'activity':activity_summary(events),'citation_corrections':citation_corrections(evidence),
            'obsolete_checks':[g for g in report.get('gaps',[]) if g in legacy],
            'notice':'这是对原报告的当前复核，原始报告和运行状态保留。目录齐全不代表数据充分或预测已验证。'}

class Factor(BaseModel):
    ingredient_id:str
    low_mg:float=Field(gt=0,allow_inf_nan=False)
    high_mg:float=Field(gt=0,allow_inf_nan=False)
class DoeInput(BaseModel):
    baseline_id:str
    filler_id:str
    factors:list[Factor]=Field(min_length=1,max_length=2)
    rationale:str=Field(min_length=3)

def design(base,request):
    items={x['id']:x for x in base['ingredients']};ids=[f.ingredient_id for f in request.factors]
    if len(set(ids))!=len(ids) or request.filler_id in ids:raise ValueError('因素不能重复或与补差辅料相同')
    if any(i not in items or items[i]['role']!='excipient' for i in [*ids,request.filler_id]):raise ValueError('仅允许基准辅料作因素与补差，API及包衣固定')
    if any(f.high_mg<=f.low_mg for f in request.factors):raise ValueError('上限必须大于下限')
    total=sum(x['amount_mg'] for x in items.values());points=[]
    for levels in itertools.product(*[(f.low_mg,(f.low_mg+f.high_mg)/2,f.high_mg) for f in request.factors]):
        amounts={k:v['amount_mg'] for k,v in items.items()};amounts.update(dict(zip(ids,levels)))
        amounts[request.filler_id]=total-sum(v for k,v in amounts.items() if k!=request.filler_id)
        if not math.isfinite(amounts[request.filler_id]) or amounts[request.filler_id]<=0:raise ValueError('范围产生非正补差用量，请缩小因素范围；未保存任何组合')
        points.append({'number':len(points)+1,'amounts_mg':amounts,'total_mg':total})
    return {'baseline_id':base['id'],'baseline_snapshot':base,'request':request.model_dump(),'points':points,'status':'三水平候选设计；非模拟结果、非已执行实验','limitations':['范围由用户设定，尚未由证据验证','补差导致混合物约束，不能当作各组分独立效应','未随机化、未配置独立重复或功效；不是完整实验执行方案','没有自动生成溶出率、响应面或最优处方']}

ORGANIZE_POLICY += " 数据组织职责：分别保留实验室数据、他方检测报告、文献检索资料的来源身份，当前项目数据是关联视图而非第四种来源。整理时保留物料/厂家/规格/批次/方法/单位/原文位置与适用范围；来源未明确则待归类，不凭厂家名称将资料判为检测报告。原始测量、限度、典型值、读图估值、模型与校准成果不混为一类。历史资料累积与去重不等于全部已核验，不把被用于拟合的数据称为独立验证。"

ORGANIZE_POLICY += " 02资料入口进一步区分辅料检测数据与实验室制剂辅料优化数据：前者是单物料检测，后者是完整处方、物料批次、工艺与性能实测。制剂优化数据关联单辅料档案但不合并为单辅料属性，不把模型预测登记为实验。"


def organization_scope(include_coating):
    if include_coating:
        return '【本轮范围：包衣同步研究=开启】按本轮目录整理片芯辅料、包衣及其关联；片芯配对与片芯—包衣关联分开说明，不默认包衣可作等量补差。'
    return '【本轮范围：包衣同步研究=关闭】仅整理本轮目录中的片芯/内容物辅料及其配对。冻结基准中的包衣/壳仅为保留背景，不检索、不建立其材料条目或配对，不把缺包衣资料列为本轮缺口；不声称包衣没有性能影响。此范围优先于问题或历史中的全部辅料要求。'
