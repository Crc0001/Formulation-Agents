"""Conservative process evidence checks: equipment is not an operation."""
import re

def compact(text):
    return re.sub(r'\s+', '', text).casefold()

def validate_processes(processes, evidence):
    byid={e['id']:e for e in evidence}
    checked=[];issues=[]
    for process in processes:
        valid=[sid for sid in process.source_ids if sid in byid and byid[sid].get('basis')=='source' and byid[sid].get('access') in ('full_text','page_text','imported')]
        source_text=[compact(byid[sid]['text']) for sid in valid]
        steps=[]
        for step in process.steps:
            reason=''
            if not any(compact(step.action_quote) in text for text in source_text):
                reason='操作引文未能在引用原文中定位'
            # Remove equipment names before deciding whether the text describes granulation.
            action=re.sub(r'湿法混合制粒机|摇摆式制粒机|万能粉碎机|wet\s+(?:mixing\s+)?granulator|oscillating\s+granulator','',step.action_quote,flags=re.I)
            if step.operation=='wet_granulation' and not (
                re.search(r'加.{0,12}(水|溶液|黏合液|粘合液|乙醇)|润湿|湿颗粒|湿法制粒|wet\s+granulat|moisten|binder\s+solution',action,re.I)
                and re.search(r'制粒|造粒|颗粒|granulat',action,re.I)):
                reason='缺少湿法制粒操作证据，不能由设备名称推定'
            if step.operation=='dry_granulation' and not re.search(r'干法制粒|辊压|压实|压块|干颗粒|roller\s+compact|dry\s+granulat|slugging',action,re.I):
                reason='缺少压实或干法制粒操作证据'
            cues={
                'premix':r'预混|premix|pre-mix',
                'milling':r'进行粉碎|粉碎两次|粉碎\s*\d|研磨|共粉碎|milled|milling|ground|pulveriz|comminut',
                'sieving':r'进行过筛|过.{0,8}筛|siev|screen|passed through',
                'blending':r'混合|总混|mixed|mixing|blend',
                'lubrication':r'硬脂酸|滑石粉|stearat|talc|lubric',
                'filling':r'填充|充填|灌装|\bfill\b|filled|filling|encapsulat',
                'polishing':r'进行抛光|抛光后|polish',
                'drying':r'干燥|烘干|drying|dried',
            }
            if step.operation in cues and not re.search(cues[step.operation],action,re.I):
                reason='引文未找到该实际操作的明确表述，不能补写步骤'
            # Prevent numeric settings unsupported by the step quote from surviving as sourced parameters.
            numbers=set(re.findall(r'\d+(?:\.\d+)?',step.parameters))
            if not numbers.issubset(set(re.findall(r'\d+(?:\.\d+)?',step.action_quote))):
                reason='参数数值未出现在该步骤的原文引文中'
            if reason:
                issues.append(f'{process.title} / 步骤{step.order}：{reason}；保留待核。')
                step=step.model_copy(update={'operation':'unknown','parameters':''})
            steps.append(step)
        checked.append(process.model_copy(update={'steps':steps,'source_ids':valid,'source_role':process.source_role if valid else 'unknown'}))
    return checked,issues
