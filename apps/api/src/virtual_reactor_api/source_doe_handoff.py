"""Immutable source-only 03→04 handoff, with held-out responses stored separately."""
import copy,hashlib,json,re

def prepare(record):
 result=record['result'];arms=result.get('arms',[])
 if result.get('version')!='image-source-model-v1' or len(arms)!=3:raise ValueError('当前交接要求同源三个用量水平的估读模型')
 levels=[]
 for a in arms:
  m=re.search(r'(?<![\d.])(\d+(?:\.\d+)?)\s*%\s*w/w',a['label'])
  if not m or 'V60' not in a['label']:raise ValueError('当前已接通V60三水平案例；其它案例须先明确因素身份及单位')
  levels.append((float(m[1]),a))
 levels.sort(key=lambda x:x[0])
 if [x[0] for x in levels]!=[5,7.5,10]:raise ValueError('V60交接需5%、7.5%、10%三个明确水平')
 snapshots=result.get('inputs',[])
 if len({v['source']['sha256'] for v in snapshots})!=1:raise ValueError('不是同源图像')
 def raw(level,a):
  return dict(level=level,label=a['label'],source_id=a['source_id'],points=copy.deepcopy(a['points']))
 training=[raw(*levels[0]),raw(*levels[2])];held=raw(*levels[1])
 public=dict(version='source-doe-handoff-v1',source_model_id=record['id'],source_input_hash=result['input_hash'],baseline_id=record['baseline_id'],factor='V60玉米淀粉含量',unit='% w/w（全制剂质量百分数，按文献标示）',training=training,heldout_level=7.5,heldout_point_count=len(held['points']),status='ready_for_source_validation',
 protocol=dict(model='lag_first_order',mapping='端点分别重新拟合；Qinf、tau、lag按用量作线性插值',training_levels=[5,10],heldout_level=7.5,validation='冻结整条预测曲线后才能读取留出响应进行误差比较',parameter_origin='不得使用03对全部三水平选出的参数或模型比较结果',execution='pending'),
 limitations=['这是已经查看过中间曲线后的回顾性留出验证，不是真正盲法或独立外部验证。','图中估读身份和读图误差保留，不能当原始实验表值。','本接口不确认乳糖等量补差、不产生甲钴胺预测、不修改处方或启动实验。'])
 key=hashlib.sha256(json.dumps({'public':public,'heldout':held},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 public['handoff_hash']=key
 return public,dict(handoff_hash=key,heldout=held)
