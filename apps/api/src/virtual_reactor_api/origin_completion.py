"""Operational delivery checks, distinct from scientific completeness."""
def delivery_issues(report, stage=None):
    if not report:return ['尚无报告']
    if hasattr(report,'model_dump'):report=report.model_dump()
    gaps=report.get('gaps',[])
    prefixes=('候选比较尚未完成（','比较表引用缺失：','第一阶段未交付：','分段整理待续：')
    issues=[g for g in gaps if g.startswith(prefixes) or ('来源段 ' in g and '提取未完成（' in g)]
    if report.get('summary') in ('正在逐段整理归档来源','归档来源尚未提取出可交接处方；已保存进度及具体缺口。'):
        issues.append('报告仍为提取阶段稿')
    comparison=report.get('decision_comparison') or {}
    if stage in (1,3) and not comparison.get('rows'):issues.append('本阶段尚未交付结构化比较表')
    if stage==1:
        from .origin_stages import IDENTITY_ROWS
        rows={r.get('metric') for r in comparison.get('rows',[]) if r.get('values')}
        issues.extend('第一阶段未交付：'+name for name in IDENTITY_ROWS if name not in rows)
    return list(dict.fromkeys(issues))


STATUS_LABELS = {
    'running': '研究中', 'queued': '等待派单', 'awaiting_resume': '待自动接续',
    'rate_limited': '接口限流，等待冷却', 'timeout': '请求超时，待接续',
    'provider_error': '接口故障，待排障', 'delivery_error': '整理或校验失败，待修复',
    'cancelled': '已取消', 'interrupted': '运行中断，待接续',
    'no_progress': '接续无进展，待排障', 'delivered': '三阶段已交付，待科学核验',
}


def execution_detail(item, run=None, events=(), supervision=None):
    """Operational state from this attempt only; never infer human-only science work."""
    import re
    run = run or {}
    phase = (item.get('phases') or [{}])[-1].get('phase')
    report = run.get('report') or {}
    issues = delivery_issues(report, phase) if run else []
    pending = next((int(m.group(1)) for g in report.get('gaps', [])
                    if (m := re.match(r'分段整理待续：(\d+)段', g))), 0)
    code, reason = 'awaiting_resume', '本阶段交付未完成，可从已保存进度接续。'
    error_types = []
    for e in events:
        if e.get('kind') in ('model_error', 'provider_failure', 'origin_extract_error', 'origin_decision_error'):
            payload = e.get('payload') or {}
            error_types.append(str(payload.get('error_type') or payload.get('type') or payload.get('category') or ''))
    # Do not interpret accumulated historical report gaps as a new provider failure.
    direct_error = str(run.get('error') or '')
    if direct_error.startswith('阶段交付未完成：'):
        direct_error = ''  # This field repeats accumulated report gaps, not a new API error.
    failure = ' '.join(error_types[-1:]) + ' ' + direct_error
    if re.search(r'RateLimit|HTTP\s*429', failure, re.I):
        code, reason = 'rate_limited', '本轮接口限流；冷却后接续，不能仅凭429判断余额不足。'
    elif re.search(r'Timeout|超时', failure, re.I):
        code, reason = 'timeout', '本轮请求超时；已保存段落保留，从未完成部分接续。'
    elif re.search(r'Authentication|Permission|NotFound|Connection|APIError|HTTP', failure, re.I):
        code, reason = 'provider_error', '本轮模型接口异常，需要排查配置或连接。'
    elif failure.strip() or any(g.startswith(('比较表引用缺失：', '候选比较尚未完成（')) for g in issues):
        code, reason = 'delivery_error', '本轮整理或结构校验未通过，不能当作科学核验完成。'
    if run.get('status') == 'interrupted':
        code, reason = 'interrupted', '运行中断，已保存资料可接续。'
    if run.get('status') == 'cancelled':
        code, reason = 'cancelled', '本轮已取消，保留历史；需要明确安排接续。'
    if item.get('status') == '三阶段已交付，待逐项验收':
        code, reason = 'delivered', '程序已交付三阶段报告；来源与结论仍待科学核验。'
    control = supervision or {}
    if control.get('run_id') == run.get('id') and control.get('status') == 'no_progress':
        code, reason = 'no_progress', '连续接续未取得新进展，已停止重复调用，需排查程序或接口。'
    if item.get('status') == '排队' or item.get('retry_request'):
        code, reason = 'queued', '已安排从保存进度继续。'
        phase = (item.get('retry_request') or {}).get('phase', len(item.get('phases', [])) + 1)
    if run.get('status') in ('running', 'queued'):
        code, reason = 'running', '本轮正在研究并保存阶段成果。'
    return dict(name=item['name'], project_id=item.get('project_id'), phase=phase,
                run_id=run.get('id'), code=code, label=STATUS_LABELS[code], reason=reason,
                pending_chunks=pending, completed_chunks=len(set(report.get('origin_extraction_done', []))),
                scientific_status='尚未科学核验', requires_human_verification=None)
