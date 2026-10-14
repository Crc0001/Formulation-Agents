"""Depth requirements for explicit topics; checks activity, not scientific truth."""
RESEARCH_DEPTH = """
处方溶出行为专项与药典单点放行核验分开。执行顺序：
1. 盘点已有处方和证据，列出产品/实施例—工艺—介质—时间点的缺口矩阵。
2. 使用google、patents、scholar三种引擎，查药物盐名/英文名/商品名+ dissolution profile、release、formulation、stability；原研厂家专利族和引用链；论文全文与补充表；官方/厂家方法。至少覆盖三类来源路径，失败换入口，不能只重复药典转载。
3. 优先读取已有命中的专利表格，再扩展到原研与自制的同方法对照、多pH/转速、辅料/工艺变更和储存前后变化。没有差异实验不能归因某个辅料。
4. 原表可读数字写入dissolution_curves：一条记录只含一个处方/样品、介质、方法及储存状态；formula_title精确匹配本报告formulations.title，原研对照处方未知也单独建记录并保留空components，不能绑定到专利自制处方。引用必须与处方共享已读取的原文证据，table_excerpt逐字保存包含时间/溶出数据的原表文本。只有图片未实际识图时留缺口，不构造曲线。不把f2、30分钟限度或崩解时间当曲线。
5. method列装置/体积/转速/温度，sample列批次/n，storage列储存条件与时长；未公开逐项明确标记。指出方法不同不可直接对比、原文数字/行列对应仍需复核。数值不能静默裁到100%。
6. findings总结可比曲线变化及实际支持的开发判断，gaps逐项给失败原因、待取表图和下一条查询。发现有价值表格后继续完成提取，不只抄摘要；没有取得曲线不能宣称专项完成。
批处方必须提取明确批量粒数batch_units和每项batch_amount、batch_mass_unit（mg/g/kg），服务端统一计算amount_mg为每粒/片mg；保留原始数量和单位。已标明单粒的amount_mg不得重复除以批量。只有重量份而无粒数时不得猜粒数，保留比例与缺口。
专项研究应先盘点当前项目已经取得的处方和工艺，沿缺口继续，不只做一次宽泛搜索。
官方处方：按市场/版本追查说明书、注册审评和定量附件，记录查过哪些国家，转载不能等同监管原件。
专利处方工艺：从原研厂家及别名查专利族、优先权、前后引用，再逐实施例读取；区分商业产品、专利对照和仿制方案。
文献处方工艺：论文/学位、全文、补充材料、引用链，重点提取材料表、制备步骤及对应性能。
所选专项至少尝试两种实质不同的查询路径并读取原文。失败换入口，预算不足如实结束，不重复相同查询凑数。
每张处方单独写入formulations，工艺写入processes，不仅写在summary。重量份在locator保留各成分原始份数与总份数，明确共同分母时写percent，不能转成mg。不得合并不同实施例。
逐辅料研究用途、加入位置、等级、在当前工艺中的机制、影响指标、范围、交互作用和证据。amount_basis未知不代表功能未知，功能放入excipients发现。无受控实验不得给固定贡献分数。
性能结果须绑定产品/实施例与检测条件，崩解、硬度不代替溶出。报告逐渠道列实际查询、读取状态、用量取得状态、未解决原因及下一条具体查询。
"""
def research_requirements(message):
    if any(w in message for w in ('处方对应的溶出','处方溶出行为','深入研究溶出')) and '【专项：' not in message:
        return ('处方溶出行为',{'regulatory','manufacturer','patents','literature','japan'},False)
    topics={
      '【专项：处方溶出行为】':('处方溶出行为',{'regulatory','manufacturer','patents','literature','japan'},False),
      '【专项：官方处方】':('官方处方',{'regulatory','anmat','japan','manufacturer'},True),
      '【专项：专利处方工艺】':('专利处方工艺',{'patents'},True),
      '【专项：文献处方工艺】':('文献处方工艺',{'literature'},True),
      '【专项：辅料功能】':('辅料功能',{'manufacturer','technical','literature'},False),
      '【专项：工艺性能】':('工艺性能',{'regulatory','manufacturer','patents','literature','technical','japan'},False),
    }
    return next((v for k,v in topics.items() if k in message),None)
def research_gaps(required,events,report):
    if not required: return []
    name,channels,needs_formula=required
    queries={' '.join(e['payload'].get('query','').lower().split()) for e in events if e['kind']=='coverage_search' and e['payload'].get('channel') in channels and e['payload'].get('query')}
    read=any(e['kind']=='coverage_document' and e['payload'].get('channel') in channels for e in events)
    gaps=[]
    if len(queries)<2: gaps.append(name+'：尚未记录至少两条不同查询，需沿原文附件、别名或引用链继续。')
    if not read: gaps.append(name+'：尚未取得对应渠道原文，不能将搜索摘要当处方证据。')
    if needs_formula and not report.formulations: gaps.append(name+'：尚未形成逐来源结构化处方；已读到处方表时请提取，否则明确未取得原因。')
    if name=='处方溶出行为':
        engines={e['payload'].get('engine') for e in events if e['kind']=='coverage_search'}
        for engine in ('google','patents','scholar'):
            paths={e['payload'].get('query','').strip().lower() for e in events if e['kind']=='coverage_search' and e['payload'].get('engine')==engine}
            if len(paths)<2: gaps.append('处方溶出行为：'+engine+'尚未覆盖两条不同查询路径；需沿药物别名、原研厂家、处方实施例或引用链继续。')
        if not getattr(report,'dissolution_curves',[]): gaps.append('处方溶出行为：尚无通过原文与处方关联检查的逐点曲线，请继续读取表格；图像不可读或公开资料确实不足时明确记录缺口。')
    return gaps
