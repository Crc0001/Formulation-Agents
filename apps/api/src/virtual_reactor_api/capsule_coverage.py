"""Source coverage derived from durable tool events, never a model's completion claim."""
from typing import Literal
from .capsule_models import CoverageItem, CoverageView, SourceChannel

CHANNELS = {
    'regulatory': ('各国注册与审评资料', '核对监管原文、产品、厂家、规格、市场及版本；寻找定量批准附件。'),
    'anmat': ('阿根廷 ANMAT', '使用西班牙文通用名、商品名、composición、fórmula及批准附件检索；不预设必然公开用量。'),
    'japan': ('日本 IF 与官方质量资料', '用日文通用名查 PMDA、NIHS 和厂商 IF；未上市或无适用品种须有依据。'),
    'manufacturer': ('原研厂家与历史版本', '查不同市场的官方产品资料与历史版本，分别记录处方，不能跨市场合并。'),
    'patents': ('专利族与引用链', '读取优先权、同族、引用及被引文献的具体实例，区分对照处方和商业处方。'),
    'literature': ('论文与学位资料', '检索实际处方筛选、工艺及 BE 研究；查全文，记录研究对象和配方关联。'),
    'technical': ('企业技术与监管公示', '查公开技术资料及环评附件；投入量不能未经批量核验直接换算成每粒处方。'),
    'other': ('其他及历史未分类记录', '旧运行没有渠道记录，保留查询，不倒推已覆盖哪些渠道。'),
}

def coverage(store, pid):
    store.project(pid)
    grouped = {k: {'searches': [], 'documents': []} for k in CHANNELS}
    evidence = {e['id']: e for e in store.rows('evidence', pid)}
    for run in store.rows('runs', pid):
        events = store.events(run['id'])
        classified_queries={e['payload'].get('query') for e in events if e['kind']=='coverage_search'}
        for event in events:
            p = event['payload']
            channel = p.get('channel', 'other')
            if channel not in grouped: channel = 'other'
            base = {'run_id': run['id'], 'created_at': event['created_at']}
            if event['kind'] == 'coverage_search':
                grouped[channel]['searches'].append({**base, **p})
            elif event['kind'] == 'search_completed' and p.get('query') not in classified_queries:
                grouped['other']['searches'].append({**base, 'query':p.get('query',''), 'engine':p.get('engine',''), 'status':'历史查询，结果待核'})
            elif event['kind'] == 'search_error' and p.get('query') not in classified_queries:
                grouped['other']['searches'].append({**base, 'query':p.get('query',''), 'engine':p.get('engine',''), 'status':'历史查询失败', 'error':p.get('error','')})
            elif event['kind'] == 'coverage_document':
                sid = p.get('evidence_id')
                # An event cannot claim retrieval using another project's evidence.
                valid = sid in evidence and evidence[sid].get('run_id') == run['id']
                grouped[channel]['documents'].append({**base, **p, 'status': '取得正文，待核适用性' if valid else '读取失败', 'evidence_id': sid if valid else None})
    recorded={d.get('evidence_id') for g in grouped.values() for d in g['documents']}
    for e in evidence.values():
        if e['id'] not in recorded and e.get('run_id') and e.get('access') in ('full_text','page_text'):
            grouped['other']['documents'].append({'run_id':e['run_id'],'created_at':e['created_at'],'evidence_id':e['id'],'title':e['title'],'url':e.get('source_url',''),'status':'历史正文，渠道未分类，适用性待核'})
    items=[]
    for k,(title,objective) in CHANNELS.items():
        g=grouped[k]
        status = '尚未检索'
        if g['searches'] or g['documents']: status='已尝试，原文仍有缺口'
        if any(d.get('evidence_id') for d in g['documents']): status='已取得部分正文，仍需核验'
        items.append(CoverageItem(channel=k,title=title,objective=objective,status=status,**g))
    return CoverageView(project_id=pid,items=items)
