"""Evidence-based formulation screening, independent of quantitative prediction."""
PREFIX='【处方辅料筛选】'
PROMPT="""本轮主目标为药品处方及辅料筛选，优先于历史性能预测任务及旧技能的强制模拟流程。
明确目标API、剂型、规格、市场与当前完整处方。结合实际用途筛选辅料及牌号/粒度/加入方式。
保留两个必答轴：API粒度匹配（分散、均匀性、偏析、润湿/溶解；区分d10/d50/d90、测法与团聚），工艺匹配（直混/制粒、加料顺序、润滑、压实/填充）。未知必须写明，不给无依据的最佳粒径或最佳工艺。
输出screening_candidates：每个候选填写title、disposition(test_first优先试验/reserve备选/exclude暂不选/insufficient待补证据)、formulation完整方案身份与差异、excipient_selection、api_particle_match、process_match、rationale、source_ids、uncertainties、verification_experiment、decision_rule。
优先试验只是研发排序，不是性能优胜或批准采纳。无来源时只能insufficient；少量有区分度的候选胜于凑数。每个候选给可执行配对验证与判定规则，无依据的数值阈值明确待预设。
只查与本轮筛选有关渠道，读取原文，图片表按需读图。优先复用已归档原文和核验记录，不反复复制整段历史。来源与用户输入、候选假设严格区分。
不要求生成溶出预测、模拟残差、硬度/崩解定量预测或双栏模型报告；缺这些不是筛选失败。必须交付筛选卡、依据、粒度和工艺匹配及具体验证实验。科学缺口如实保留，不自动写入处方/参数/实验。最终ResearchReport保持简洁，历史处方无需重复全量输出。
"""
def validate_candidates(candidates,evidence):
    readable={e['id'] for e in evidence if e.get('basis') in ('source','image_estimate','measurement') and e.get('access') in ('full_text','page_text','imported','user')}
    result=[];issues=[]
    for c in candidates:
        valid=[sid for sid in c.source_ids if sid in readable]
        update={'source_ids':valid}
        if not valid or len(valid)!=len(c.source_ids):
            update['disposition']='insufficient'
            update['uncertainties']=list(dict.fromkeys(c.uncertainties+['候选引用需补充可读取的原始证据；暂不作为试验优先级依据。']))
            issues.append(c.title+'：候选原始证据不足')
        for field in ('formulation','excipient_selection','api_particle_match','process_match','rationale','verification_experiment','decision_rule'):
            if not getattr(c,field).strip():
                update['disposition']='insufficient';issues.append(c.title+'：缺少'+field)
        result.append(c.model_copy(update=update))
    return result,issues

# A bounded delivery contract; absence of target measurements is not a retrieval failure.
PROMPT += """
对于用户明确的替换比较，首要交付substitution_assessment，而不是推荐新的物料分支。
actual_change逐项锁定本轮数值差异；source_identity核对来源ID实际文献身份，错配须明确，不沿用行内旧备注覆盖本轮数值；answer直接回答本次替换已有证据支持什么，不把优先试验写成性能优胜。
supported写可支持的机制/方向及其条件，unresolved仅列真正阻止目标判断的关键未知，next_action给解决首要缺口的具体动作。
cases逐个提供原始对照：title、source_id、locator、source_quote（原文连续逐字摘录）、change（来源两臂实际组成变化）、observed_result（实测值或作者明确报告的定性结果）、comparability、limitation。必须实际读取对应原文；无逐点数值可引用作者定性结果，不从f2反造曲线。
没有找到可用对照时cases可空，但须在unresolved写明实际查过的路径与未取得什么，不能虚构。候选仅保留用户当前方案及其对照，用户未要求时不扩展新牌号。来源数据、目标推断、待验证条件分开写。
校验失败后只补指定原文/引文缺口，返回完整修订报告；不要重新搜索无关渠道。无需重复输出来源处方和工艺结构，除非本轮确实新增或修正了它们。
"""

def validate_assessment(assessment,evidence):
    if assessment is None:
        return ['未交付替换对照分析']
    import re
    by_id={e['id']:e for e in evidence}
    norm=lambda s:re.sub(r'\s+','',s).casefold()
    issues=[]
    for c in assessment.cases:
        e=by_id.get(c.source_id)
        if not e or e.get('basis') not in ('source','image_estimate','measurement'):
            issues.append(c.title+'：对照来源无效');continue
        if not c.source_quote.strip() or norm(c.source_quote) not in norm(e.get('text','')):
            issues.append(c.title+'：对照原文摘录未匹配，须读取原文后修正')
    for field in ('actual_change','source_identity','answer','supported','unresolved','next_action'):
        if not getattr(assessment,field).strip():issues.append('替换分析缺少'+field)
    return issues
