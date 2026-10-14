"""Resolve baseline citations without promoting OCR to verified source data."""
def baseline_sources(ids,sources):
    resolved=list(dict.fromkeys(ids));warnings=[]
    def readable(e):
        return e and e.get('basis') in ('source','measurement') and e.get('access') in ('full_text','page_text','imported','user')
    for eid in ids:
        e=sources.get(eid)
        if readable(e):continue
        if e and e.get('basis')=='image_estimate' and e.get('access')=='imported':
            f=e.get('fields',{});parent_id=f.get('source_evidence_id');parent=sources.get(parent_id)
            digest=f.get('source_document_sha256')
            if readable(parent) and digest and digest==parent.get('fields',{}).get('sha256'):
                if parent_id not in resolved:resolved.append(parent_id)
                warnings.append('图片识别用量待核验：'+e.get('title',eid)+'；保存为研究基准不表示OCR数值已经验证。')
                continue
        raise ValueError('无法保存基准：'+(e.get('title',eid) if e else eid)+'缺少本项目可读取原文或可核对的原图关联。请核对来源；搜索摘要不能代替原文。')
    return resolved,warnings
