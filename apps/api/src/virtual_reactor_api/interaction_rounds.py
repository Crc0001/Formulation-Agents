"""Bounded topic research, durable round reports, no automatic scientific adoption."""
import json
from .interaction_agent import research_increment
from .origin_delivery import merge_report

ROUND_TASKS = [
 '来源案例筛选：不限药物或BCS，比较目标辅料变化的候选原文。按组成与工艺可比性、可读原表、因素水平及验证数据完整性选定一个来源案例，填写source_case；优先溶出，物性案例明确指标。不要继续被目标药缺数据阻断。',
 '来源模型复现：围绕选定案例读取原表与条件，调用注册工具计算来源关系，交付原始点、方程、单位、残差及适用范围。用文献检验机制及反证；数据不够则换更完整案例并说明原因，不凭药名或辅料名生成系数。',
 '来源复验与目标迁移分开：检查程序内部留出结果、误差及失效条件；有独立未参与拟合的数据才做独立验证，否则明确缺口。更新source_case验证等级及结果，给出可保留或应否定的来源假设，再单列目标迁移条件。目标缺数据不撤销已经完成的来源计算。'
]

async def run_topic(store,rid,root,runner,save_round,baseline_id,target):
    original=store.run(rid)['message']; pid=store.run(rid)['project_id']; history=[]; accumulated=None
    names={x['id']:x['name'] for x in target['materials']}
    topic='—'.join(names.values())+'对片剂性能的影响' if '片' in target['dosage_context'] else '—'.join(names.values())+'性能专题'
    for number,task in enumerate(ROUND_TASKS,1):
        before=store.rows('evidence',pid)
        if len(names)==2:
            task=[
                '典型制剂选案与三线核对：围绕指定辅料，优先筛选组成、补差、工艺及响应数据完整的直接互换或混合设计案例，填写source_case选案理由；同时整理两条单物料变化及直接互换三线。不限药物，不强求目标同药，不默认固定乳糖或淀粉优先级。已有可复算案例则沿用并补缺，不反复从头搜索。',
                '典型制剂来源复算与图示：围绕选定案例读取原始组成和性能表，明确补差和其它共变，使用注册工具计算端点差异、来源响应或溶出关系。两点可先算差值及明确区间假设，不因无法迁移目标药而阻断；用单物料线与其它案例核对机理及反证，保留条件差异。',
                '典型制剂假设比较与迁移交付：比较本案例模型与反例、内部留出或独立验证，交付source_case及pair_synthesis；分别说明来源已算结果、未验证假设和目标映射缺口。两条单物料线不可直接相减时给出条件理由，保留已完成直接互换结果；不把来源复现称为目标预测。'
            ][number-1]
        message=original+'\n【固定研究专题】'+topic+'\n【专题轮次】'+str(number)+'/3：'+task+'\n每轮summary必须说明新增证据、与前轮判断的比较、仍未解决的问题。每轮保存阶段稿；没有新增也如实说明。最终须对前轮关键对照逐项保留、修正或否定并说明理由，不能仅省略。原图有可读点时调用digitize_source_chart，不把OCR刻度当曲线数据；图中估读与原表分开。'
        if history:message+='\n前轮报告与增量（不是已验证参数）：'+json.dumps(history,ensure_ascii=False)
        store.finish(rid,'running',message=message,report=None,error='')
        store.event(rid,'topic_round_started',{'round':number,'total':3,'topic':topic})
        await runner(store,rid,root)
        current=store.run(rid)
        if current.get('report'):
            accumulated=merge_report(accumulated,current['report']).model_dump()
            store.finish(rid,current['status'],report=accumulated)
        elif accumulated:
            store.finish(rid,current['status'],report=accumulated)
        record={'run_id':rid,'baseline_id':baseline_id,'round':number,'topic':topic,'task':task,'status':current['status'],'report':current.get('report'),'error':current.get('error',''),**research_increment(before,store.rows('evidence',pid),rid)}
        # Count only records created in this round, not earlier same-run calculations.
        oldids={e['id'] for e in before}
        record['calculation_ids']=[x for x in record['calculation_ids'] if x not in oldids]
        save_round(record);history.append(record)
        store.event(rid,'topic_round_saved',{'round':number,'status':record['status'],'new_source_files':record['new_source_files'],'calculations':len(record['calculation_ids'])})
        if current['status'] in ('failed','cancelled','interrupted') or not current.get('report'):
            break
    return history
