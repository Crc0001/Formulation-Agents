"""Shared selection contract for discovery and recovery; no invented matching scores."""
SELECTION_POLICY = '''原研及处方工艺的候选优先规则：
1. 锁定目标市场、持有人/厂家、规格、剂型及包衣类型、说明书版本和来源。日本糖衣片不能替代中国薄膜衣片；未取得目标说明书完整辅料名单时，种类匹配结论必须为未核实。
2. 将候选与目标说明书逐物料比较：相同、增加、缺少、规格/化学形态未确认；片芯与包衣分开。玉米淀粉与预胶化淀粉不合并，乳糖水合/无水及牌号未明须保留差异；原研列料未注明所在部位时不擅自归为片芯。
3. 本智能体首先还原目标原研产品的处方及工艺。优先核实官方注册/审评/产品资料和原研公司制剂专利族、对应实施例；结合申请人/权利人、优先权日、上市时间及产品版本证明关联。当期资料优先核对，但年代相近不等于商业采用。非原研公司的后续仿制、改良专利仅为辅助对照或追溯原研专利的线索，不因定量完整、曲线齐全或便于科研而升为原研首选。CN等公开国别不决定原研身份，须核对专利族及申请人。原研定量尚未取得时明确未解决，保留已有原研候选及下一步原文路径，不把第三方候选冒称原研；如只能提供第三方试验参考，明确降级及选择依据。
4. 溶出须精确绑定实施例/批次、时间点、介质、装置、体积、转速、温度，核对参比身份；f2或单点限度不能代替曲线，不同方法不直接比较。不把专利声称参比自动视为已核实目标商业批。完整性缺口如重复数/变异/未取得介质须指出。
5. 判断API粒度、用量、工艺、均匀度、稳定性及相容性是否存在反对优先选择的证据。种类相同不等于性能等效，有曲线不等于溶出更快即更好。不编造权重分数、不自动冻结。
decision_comparison必须含精确命名的四行：目标原研与版本、原研专利归属及时间关联、辅料种类匹配、对应溶出证据。逐候选填写状态、差异/缺口与真实source_ids；未取得写未核实。推荐理由须说明为何优先于其他候选、哪些条件会改变排序。'''

REQUIRED_ROWS=('中国参比目录批次及序号','参比商品名与规格','参比持有人与生产厂家','参比上市国家与生产国家','目标原研与版本','原研专利归属及时间关联','辅料种类匹配','对应溶出证据')

def audit_selection(report,project=None):
    """Missing comparisons remain explicit; never manufacture an ingredient match."""
    # Recompute this mechanical audit rather than carrying its stale verdict forward.
    prefix='推荐依据未完整交付：'
    rec=report.origin_recommendation
    report=report.model_copy(update={'gaps':[g for g in report.gaps if not g.startswith(prefix)],
        'origin_recommendation':rec.model_copy(update={'limitations':[g for g in rec.limitations if not g.startswith(prefix)]}) if rec else None})
    if not report.origin_recommendation:return report
    table=report.decision_comparison
    rows={r.metric for r in table.rows} if table else set()
    from .origin_dosage import dosage_profile
    required=tuple(dosage_profile(project)["metric"] if name=="对应溶出证据" and project is not None else name for name in REQUIRED_ROWS)
    missing=[name for name in required if name not in rows]
    f=next((f for f in report.formulations if f.title==report.origin_recommendation.formula_title),None)
    if f is not None and not any(c.amount_mg is not None or c.batch_amount is not None or c.percent is not None for c in f.components):
        note=prefix+'所选候选只有定性组成，应放在第一阶段；尚未交付定量试验参考，请比较已有定量候选，不得用官方身份替代用量。'
        rec=report.origin_recommendation.model_copy(update={'limitations':[*report.origin_recommendation.limitations,note]})
        report=report.model_copy(update={'origin_recommendation':rec,'gaps':[*report.gaps,note]})
    if not missing:return report
    note='推荐依据未完整交付：缺少'+ '、'.join(missing)+'；仅为待复核研究候选，不代表已确认原研种类一致或首选。'
    rec=report.origin_recommendation.model_copy(update={'limitations':list(dict.fromkeys([*report.origin_recommendation.limitations,note]))})
    return report.model_copy(update={'origin_recommendation':rec,'gaps':list(dict.fromkeys([*report.gaps,note]))})


SELECTION_POLICY += """
推荐须区分用途：官方定性组成仅列为第一阶段身份/组成依据，不占用最终试验参考推荐；原研关联的定量候选可以在明确未决项后暂定为研究起点，不必先证明商业采用。第三方转述原研实施例可以作为优先追溯线索，不能冒称商业确认，也不能因信息齐全替代更直接原研证据。明确列出能用于什么、缺什么、下一步由程序核对什么，不把所有用途一并判为不能确认。
当原PDF空文字或图像读取失败，先重试该物理页，仍失败则沿同族WO/US/授权文本定位同一实施例；页号不同须重新定位，不能按相同页号借用。OCR可保存为待核候选并保留OCR证据ID、原PDF父ID及页码，不改为已核验原文表值。来源引用校验失败先修复指向，不能丢掉原引用后反复泛搜。
01科研交付必须形成可核对的数据链，而非只有解释性结论：
- 对每个候选，processes.scope严格填写对应formulations.title；同一专利不同实施例或对比实施例分别关联。工艺原句、设备、参数、内外加、收率及批量单位数分别保留。
- 并列检查批量列量、单单位量、百分比；冲突时展示两值及定位，先核对收率/分母/补加阶段，不按目标规格倒推或静默改量。
- 所选候选自身溶出和原研参比曲线严格分开。文字摘要已有数值但结构化曲线为空时，优先补表头/样品列/介质/方法及原图，而非反复广泛搜索。
- 官方说明书未取得时，原研辅料种类匹配为未核实，不能同时在理由里声称已经一致。推荐依据应区分种类证据、定量完整性、工艺、性能数据和反对证据。
- 没有绑定成功程序计算记录，不把估计速率、概念方程或定性比较标source_computed；保留为待检验假设。
- 优先补最可能改变候选排序的缺口；本轮说明新增、纠正、仍缺失，旧冻结基准不自动覆盖。
"""

SELECTION_POLICY += """
01按三个阶段交付，阶段一合并原研身份和说明书：
第一阶段【原研确认与说明书组成】：展示原研企业、商品名、剂型规格、首次上市时间和地区、目标市场持有人与说明书版本及真实来源。企业/上市时间未查明明确未知，不能把现持有人等同原始研发者。列出片芯、包衣及部位未知的辅料名单。将以上身份、上市历史写入decision_comparison的“目标原研与版本”行；定性名单也保存formulations。
第二阶段【历史及专利追溯】：以第一阶段产品和上市历史倒查原研相关专利族，核对申请人、优先权及实施例关联；列出处方原始量、单位、工艺及对应性能。不能因公开国别挑选或排除；说明日本候选与异市场官方名单各自的用途。
第三阶段【比较并推荐试验参考】：目标是选出合适可做的试验参考。优先辅料种类与目标说明书相同且原研关联更直接的定量候选，再比较量的完整性、工艺、相同条件下的溶出及反对证据。缺商业采用证明不阻止暂定研究推荐；数据完整但组成不符不得仅因方便科研抢占首选。并列时说明一个优先核对对象及备选，而非用无量说明书代替比较。
origin_recommendation只用于第三阶段试验参考，formula_title必须精确指向含用量的候选；无定量候选时为空，在gaps说明下一原文路径。rationale须与decision_comparison.recommendation一致，不得正文推荐JP定量候选却在字段推荐异市场无量名单。第一阶段依据可以完整展示而第三阶段尚未完成。每阶段在summary说明已取得和下一步，复用归档来源，保留历史和冻结基准。
"""

SELECTION_POLICY += """
第一阶段必须专项检索中国NMPA/CDE参比制剂正式目录及后续增补/变更/撤销，而不是只查全球原研。decision_comparison增加四个精确行名：中国参比目录批次及序号、参比商品名与规格、参比持有人与生产厂家、参比上市国家与生产国家。逐候选给正式批次、目录序号、公告号、原始发布日期、正式/征求意见/历史状态及引用。转载日期不作公告日期，征求意见序号不可作正式序号。原研起源国、上市国家、生产国家分别记录，欧盟不猜为西班牙。持证商不是生产厂；工厂须从该版本说明书/监管记录/包装补查，未取得写未核实。同药同规格多个参比逐条列出，说明当前选用身份及其说明书匹配，不能混合其辅料名单或用量。保留证据日期，未核对后续变更不得称已确认现行。研究历史专利以这个具体产品身份为基础；不可让某异市场说明书仅因更容易获取就成为目标原研。
"""
