"""Dosage-specific research scope; routing is not a product specification."""
import re

def dosage_profile(project=None):
    project=project or {}
    if hasattr(project,'model_dump'): project=project.model_dump()
    text=' '.join(str(project.get(k) or '') for k in ('dosage_form','api','name'))
    parenteral=bool(re.search(r'注射|输液|injection|injectable|infusion',text,re.I))
    oral=not parenteral and bool(re.search(r'片剂|胶囊|tablets?|capsules?|片',text,re.I))
    kind='注射剂（具体类型须核对说明书）' if parenteral else '口服固体制剂' if oral else '其它或待确认剂型'
    if parenteral:
        for pattern,label in [(r'冻干|lyophili','冻干注射剂'),(r'脂质体|liposom','脂质体注射剂'),(r'混悬|suspension','混悬注射剂'),(r'乳剂|乳状|emulsion','乳状注射剂')]:
            if re.search(pattern,text,re.I): kind=label;break
    return {'kind':kind,'oral_solid':oral,'parenteral':parenteral,'metric':'对应溶出证据' if oral else '对应剂型质量与性能证据','basis':text,'version':'dosage-scope-v1'}

def dosage_policy(project=None):
    p=dosage_profile(project)
    return ('\n【剂型适用规则】当前项目：'+p['kind']+'。先以对应版本说明书确认实际剂型和给药途径，项目名称只用于初步路由。比较表性能行命名为“'+p['metric']+'”。'
    +('注射剂不得强制要求片剂硬度、脆碎度、崩解或常规片剂溶出。先查溶液/混悬/乳状/脂质体/冻干类型；类型未知先核对，不默认溶液。检查实际适用的含量/有关物质、pH、渗透压或等渗性、可见异物/不溶性微粒、无菌/内毒素、稳定性、包材相容性；逐项区分已取得、未取得、不适用及依据。冻干另查复溶时间/复溶后稳定性/残余水分；混悬、乳状或脂质体按产品查粒径分布、分散/包封及释放，不能一律禁止释放研究。工艺关注配液、过滤/除菌、灭菌适用性及无菌灌装，不套湿法制粒/压片。用量按原始浓度、体积、每支量和批量保留，注射用水适量不填零，不能由规格擅自倒算全部处方。' if p['parenteral'] else '按已确认剂型选质量指标；未知剂型先确认，不默认片剂。口服固体制剂保留适用的溶出、崩解及工艺核对。')
    +'非溶出性能以findings结构化记录样品/实施例、指标、数值及单位、方法条件、原文定位、source_ids；需要时调用save_source_metric。不能把pH或稳定性数值塞入dissolution_curves。只有实际适用且缺失的证据才列研究缺口。通用指标清单不是本品放行标准，不猜限度。')

def adapt_policy(text,project=None):
    if not dosage_profile(project)['oral_solid']:
        text=text.replace('对应溶出证据','对应剂型质量与性能证据').replace('溶出','剂型适用性能').replace('片芯、包衣','制剂组成及包装').replace('片芯与包衣分开','按实际制剂组成记录')
    return text+dosage_policy(project)
