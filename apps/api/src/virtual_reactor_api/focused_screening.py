"""Focused screening delivery and verifiable progress, not a validity certificate."""
from typing import Literal
from pydantic import BaseModel,Field
from .table_vision import usable_source, accepted_table

CALCULATION_FIELDS=('source_response_model_json','pair_difference_model_json','source_curve_model_json','source_metric_json','excipient_stage_json','mechanistic_chain_json','powder_yield_json','effective_rate_transfer_json','workflow_id','table_statistics_json')

def saved_calculation(e):
    return bool(e) and e.get('basis')=='hypothesis' and any(e.get('fields',{}).get(k) for k in CALCULATION_FIELDS)

class EvidenceChoice(BaseModel):
    source_id:str
    use:Literal['model_data','mechanism_only','exclude']
    reason:str=Field(min_length=3)
    factors:str
    response:str
    controls:str
    locator:str

class ResearchJudgment(BaseModel):
    preferred_hypothesis:str=Field(min_length=3,description='智能体优先支持的可检验假设；确实无法排序时明确说明，不让用户选择方向')
    expected_pattern:str=Field(min_length=3,description='预测方向及时段；定性判断不是数值预测')
    rationale:str=Field(min_length=3,description='依据可比性和反证权衡解释为何优先，或为何无法排序')
    supporting_source_ids:list[str]=Field(default_factory=list)
    counterevidence:str=Field(min_length=3)
    assumptions:str=Field(min_length=3)
    falsifier:str=Field(min_length=3)
    next_program_action:str=Field(min_length=3,description='程序下一步定向检索或计算，不把方向选择交给用户')

class EvidenceReasoningChain(BaseModel):
    source_ids:list[str]=Field(default_factory=list,description='实际采用的原始对照资料')
    source_comparison:str=Field(min_length=3,description='来源两臂组成、补差、方法及观察变化')
    calculation_ids:list[str]=Field(default_factory=list,description='真实已存程序计算记录')
    calculation_gap:str=''
    observed_relation:str=Field(min_length=3,description='来源变化到响应的关系；与机制解释分开')
    mechanism_interpretation:str=Field(min_length=3)
    target_similarities:str=Field(min_length=3)
    target_differences:str=Field(min_length=3)
    transfer_level:Literal['source_only','directional_hypothesis','conditional_quantitative']
    transfer_reason:str=Field(min_length=3)
    next_action:str=Field(min_length=3)

class MechanismComparison(BaseModel):
    stage:Literal['wetting','disintegration','dispersion','late_dissolution']
    hypothesis:str=Field(min_length=3)
    evidence_scope:Literal['same_drug','other_drug','placebo','not_found']
    paired_comparison:str=Field(min_length=3,description='两臂材料规格/用量/工艺与控制条件，单粉说明不能充当配对')
    source_ids:list[str]=Field(default_factory=list)
    calculation_ids:list[str]=Field(default_factory=list)
    response:str=Field(min_length=3,description='实际测量响应及单位；空白辅料不能填写API溶出')
    outcome:Literal['supported','weakened','contradicted','unresolved']
    interpretation:str=Field(min_length=3)
    applicability:str=Field(min_length=3)
    gap:str=''
    next_program_action:str=Field(min_length=3)

class ScreeningProgress(BaseModel):
    mechanism_comparisons:list[MechanismComparison]=Field(default_factory=list)
    reasoning_chain:EvidenceReasoningChain|None=None
    judgment:ResearchJudgment|None=None
    question:str=Field(min_length=3)
    evidence_choices:list[EvidenceChoice]=Field(default_factory=list)
    direction:Literal['increase','decrease','mixed','unknown']='unknown'
    direction_reason:str=Field(min_length=3)
    applicable_range:str
    reversal_conditions:str
    calculation_evidence_ids:list[str]=Field(default_factory=list)
    next_action:str=Field(min_length=3)
    user_action:str=Field(min_length=3)

def audit_progress(progress,evidence):
    if not progress:return {'status':'尚未交付聚焦判断','issues':['等待证据取舍和当前变化判断'],'steps':[False,False,False,False]}
    p=ScreeningProgress.model_validate(progress);sources={e['id']:e for e in evidence};issues=[]
    stages={'wetting':'进液润湿','disintegration':'解聚','dispersion':'分散与有效表面积','late_dissolution':'后期溶出'}
    seen=set()
    for c in p.mechanism_comparisons:
        if c.stage in seen:issues.append('机制研究环节重复：'+stages[c.stage])
        seen.add(c.stage)
        if c.outcome!='unresolved' and not c.source_ids:issues.append(stages[c.stage]+'：没有来源支持机制检验结果')
        for sid in c.source_ids:
            e=sources.get(sid,{})
            if not usable_source(e,evidence):issues.append(stages[c.stage]+'：原始对照引用未核对 '+sid)
        for sid in c.calculation_ids:
            e=sources.get(sid,{})
            if not saved_calculation(e):issues.append(stages[c.stage]+'：计算记录尚未核对 '+sid)
        if not c.calculation_ids and not c.gap.strip():issues.append(stages[c.stage]+'：未记录计算或具体缺口')
        if c.outcome=='unresolved':issues.append(stages[c.stage]+'：机制检验尚未完成，下一步：'+c.next_program_action)
    for stage in stages.keys()-seen:issues.append('尚未交付成对机制研究：'+stages[stage])
    if not p.judgment:issues.append('尚未交付智能体优先判断；不能仅列竞争假设后要求用户选择')
    else:
        if not p.judgment.supporting_source_ids:issues.append('优先判断尚无引用依据，不能当作有证据支持的推荐')
        for sid in p.judgment.supporting_source_ids:
            if sid not in sources:issues.append(sid+'：优先判断引用未绑定项目资料')
    chain=p.reasoning_chain
    if not chain:issues.append('缺少来源对照→程序复验→观察关系→目标迁移判断的研究链')
    else:
        for sid in chain.source_ids:
            e=sources.get(sid)
            if not e or not usable_source(e,evidence):issues.append(sid+'：研究链来源未绑定原始全文')
        if not chain.source_ids:issues.append('研究链尚无原始对照来源')
        if not chain.calculation_ids and not chain.calculation_gap.strip():issues.append('未执行来源复验且未说明具体计算缺口')
        for sid in chain.calculation_ids:
            e=sources.get(sid)
            if not e or not saved_calculation(e):issues.append(sid+'：研究链计算未绑定程序记录')
        if chain.transfer_level=='conditional_quantitative':
            if not any(sources.get(sid,{}).get('fields',{}).get(k) for sid in chain.calculation_ids for k in ['effective_rate_transfer_json','mechanistic_chain_json']):issues.append('来源拟合不能单独支持定量迁移；缺少目标计算记录')
    for x in p.evidence_choices:
        e=sources.get(x.source_id)
        if not e or e.get('access') not in ('full_text','page_text','imported','user'):issues.append(x.source_id+'：未绑定可读取原文')
        elif x.use=='model_data' and e.get('basis') not in ('source','measurement') and not accepted_table(e,evidence):issues.append(x.source_id+'：计算或假设不能当原始数据')
    for sid in p.calculation_evidence_ids:
        e=sources.get(sid)
        if not e or not saved_calculation(e):issues.append(sid+'：尚未核对为程序计算记录')
    if p.direction!='unknown' and not any(x.use!='exclude' for x in p.evidence_choices):issues.append('方向判断没有绑定采用的来源')
    return {'status':'结构化阶段判断，非预测有效性认证','issues':issues,'steps':[True,bool(p.evidence_choices) and not any('原文' in x or '原始数据' in x or '原始对照引用未核对' in x for x in issues),bool(p.calculation_evidence_ids) and not any('计算记录' in x for x in issues),not issues]}

class ScreeningSynthesisDue(RuntimeError):pass

class ScreeningBudget:
    def __init__(self,iterations,deep=False):
        self.calls=0;self.limit=max(48,int(iterations)) if deep else max(3,int(iterations)//3)
    def before_call(self):
        self.calls+=1
        if self.calls>self.limit:raise ScreeningSynthesisDue('已预留独立收尾，停止继续扩展检索')

FOCUSED_POLICY='''聚焦筛选第一阶段：锁定请求中实际物料变化、补差、工艺与指标。每读到一个相关来源，按model_data（可建模对照）、mechanism_only（机制补充）、exclude（不适用）分类，说明因素、响应、固定条件和原文定位，并调用save_screening_progress保存。不把相关性当可比性；不要求每篇都可定量迁移。至少一轮数据盘点后优先调用已有计算工具复算可用数据；没有通用计算器时明确所缺模型接口，不能伪称计算。新资料若不改变判断或补关键缺口，停止扩展。最终必须交付screening_progress及research_design；即使数值不可预测，也必须逐项给出方向及依据、适用范围、可能反转条件、下一项定向研究和用户下一步操作。方向不明则写unknown并说明竞争解释，不为完成字段编造确定结论。步骤预算到达后将由独立报告整理器基于已存资料收尾，不重启广泛检索。示例一：同工艺同配对三点有逐点响应，可列model_data后复算留出。示例二：共处理且另加黏合剂、仅硬度数据，对直接混合处方溶出只能mechanism_only。示例三：不同实验方向相反，列mixed并比较介质、加入方式和压实状态，给出判别锚点。上述示例不是本项目证据。'''

async def finish_on_budget(invoke,synthesize,notify):
    """Only planned budget/graph exhaustion trigger synthesis; cancellation/provider errors propagate."""
    try:return await invoke()
    except Exception as ex:
        if not (isinstance(ex,ScreeningSynthesisDue) or type(ex).__name__=='GraphRecursionError'):raise
        notify()
        return {'structured_response':await synthesize(),'messages':[]}

FOCUSED_POLICY+=' 用户不负责选择加快、减慢或交叉。必须交付screening_progress.judgment，由智能体权衡可比原始数据、功能机理、工艺差异及反证，给出优先假设、预期时段与方向、理由、支持来源ID、反证、成立条件、推翻条件、程序下一步行动。主假设是暂定研究判断，不等于净方向已验证；direction仍可unknown。不能以两种机制都有可能代替权衡。若确实无法排序，说明决定性冲突及最小补查，程序先检索或复算，不强行猜测或让用户选答案。实验用于后续判别，不是将所有尚可检索计算的工作交回用户。'

FOCUSED_POLICY+=' 研究顺序改为来源驱动：首先盘点本项目已取得的同辅料配对原始对照，不从通用功能列表重新开始；明确组成/补差/工艺/介质及真实响应。先调用适用程序工具复现来源，比较逐点差值、残差和模型不足；点少可调用来源对照工具保留实测差值，不补造点。由观察关系提出机制解释，再比较目标相似点和关键差异，给出主假设及source_only/directional_hypothesis/conditional_quantitative迁移等级。来源两个独立拟合不等于用量效应模型。必须填写screening_progress.reasoning_chain。工具失败先修正合法输入；仍受阻说明具体缺口，不跳过来源直接给空泛假设，不重复全面检索。source_only也必须解释为什么不迁移及下一项最小补查。'

FOCUSED_POLICY+=' 03深度研究须完成一轮假设检验而非只列假设：先针对实际变化提出分散/润湿/解聚竞争解释，逐个找到支持与反驳它的原始对照；调用来源计算，检查方向、时间依赖和残差；据此修正主假设，说明保留、削弱或推翻的理由与证据。将这一轮过程写入findings（section=comparison），标题为“机制假设的文献检验与修正”。优先利用已有原文；搜索失败不等于已有数据不可计算。来源趋势图由工具保存的实际数据生成；目标有适用映射才计算分钟/百分比曲线，否则给具明确时间段的定性趋势，不能制造幅度。工具校验失败需根据具体行和数字错误修正输入再试，最多同错误两次后改查数据定位，不能用反复读历史报告耗尽预算。'

FOCUSED_POLICY+=' 覆盖完整释放过程，不以早期解聚结论结束：mechanism_comparisons须逐项交付wetting进液润湿、disintegration解聚、dispersion解聚后分散/团聚及有效表面积、late_dissolution后期传质/溶解与平台。每项先核对已存成对原文，不足时依次扩展到其他药物同配对、空白辅料物理混合/压片研究；不能因没有甲钴胺论文转交用户实验。允许同一优质研究覆盖多个环节，但必须注明其实际测量响应及混杂，不以篇数堆砌。原生淀粉与预胶化/改性淀粉分别标身份。每项记录来源两臂条件、指标单位、程序计算ID或具体缺口、检验后支持/削弱/反驳/未决、目标适用域及下一步。空白辅料可约束接触角/吸液/孔隙/强度/崩解，不能伪装API溶出；单独崩解时间不能代替分散粒径或后期溶解。优先使用来源溶出对照工具或source_metric等已注册工具保留图形，能计算才声明模拟，只有观察值时标来源观察。早期和后期证据相反时保留时段差异，主假设必须综合四环节并说明抵消/反转条件。未决环节仍需列出真实检索范围、失败与最小补查，不得用“无本品数据”作为通用停止理由。'
