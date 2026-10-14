"""Bound provider waiting and failed publication without inventing scientific results."""
import asyncio
import hashlib
from copy import deepcopy

def provider_failure(ex):
    """Whitelist metadata only: never persist exception body, headers or request URLs."""
    from openai import APIError
    from httpx import TransportError
    if type(ex) is ValueError and str(ex).strip() == 'No generations found in stream.':
        return {'error_type':'EmptyModelStream','http_status':None,'retryable':True,
                'reason':'模型流式响应结束，但没有返回有效内容'}
    if not isinstance(ex, (APIError, TimeoutError, TransportError)):
        return None
    code=getattr(ex,'status_code',None)
    code=code if isinstance(code,int) else None
    retryable=isinstance(ex,TimeoutError) or code is None or code in (408,409,429) or code>=500
    return {'error_type':type(ex).__name__,'http_status':code,'retryable':retryable,
            'reason':'模型连接或响应中断' if code is None else f'模型接口返回HTTP {code}'}

def compact_tool_messages(messages, archive, threshold=60000, keep_recent=8):
    """Retain call IDs and full archived results; shorten only older tool bodies."""
    if sum(len(str(m.content)) for m in messages)<threshold:
        return messages,0
    result=[]; count=0
    for i,m in enumerate(messages):
        body=m.content
        if m.type=='tool' and i<len(messages)-keep_recent and isinstance(body,str) and len(body)>2400:
            digest=hashlib.sha256(body.encode()).hexdigest()[:24]
            path=f'context/tool-{digest}.json'
            archive(path,{'tool_call_id':m.tool_call_id,'content':body})
            # Exact prefix and suffix, not an AI-generated substitute for the source.
            excerpt=body[:1600]+'\n[中段已省略；完整工具结果位于 /'+path+'，需核对时用read_file读取。不得把摘录当完整原文。]\n'+body[-400:]
            m=m.model_copy(update={'content':excerpt});count+=1
        result.append(m)
    return result,count

async def invoke_with_recovery(invoke, initial, recovery, on_recovery):
    """One fresh-context recovery only; cancellation and a second failure propagate."""
    try:
        return await invoke(initial)
    except Exception as ex:
        failure=provider_failure(ex)
        if not failure or not failure['retryable']:raise
        on_recovery()
        return await invoke(recovery())

def is_summary_recovery(message):
    if message.startswith('【角色：辅料相互作用】'):
        message=message.split('\n本轮问题：',1)[-1].lstrip()
    if message.startswith('【处方辅料筛选】'):
        message=message.split('\n问题：',1)[-1]
    message=message.removeprefix('【原研及处方工艺】').lstrip()
    return message.startswith('【接续：汇总】') or message.startswith('继续完成上次因程序120秒总时限而中断的最终汇总。本轮是已有研究成果的恢复收尾')

def report_sources(evidence):
    """Full saved text without OCR geometry, repeated metadata, or tool history."""
    seen=set(); result=[]
    for e in evidence:
        identity=(e.get('source_url'),e.get('locator'),e['text'],e['basis'])
        if identity in seen:continue
        seen.add(identity)
        result.append({k:e.get(k) for k in ('id','title','text','basis','access','source_url','locator','applicability')})
    return result

class PublicationLimitError(RuntimeError):
    pass

class PublicationGuard:
    def __init__(self):
        self.failures=0
    def check(self):
        if self.failures>=2:
            raise PublicationLimitError('归档连续失败两次，停止重复尝试；已取得资料保留')
    def failed(self):
        self.failures+=1
    def success(self):
        self.failures=0

async def bounded_model_call(handler,request,seconds=120,on_wait=None,interval=30):
    task=asyncio.create_task(handler(request))
    start=asyncio.get_running_loop().time()
    try:
        while True:
            elapsed=asyncio.get_running_loop().time()-start
            remaining=seconds-elapsed
            if remaining<=0:raise TimeoutError(f'模型单次请求超过{seconds}秒等待上限；已保存成果保留')
            done,_=await asyncio.wait({task},timeout=min(interval,remaining))
            if done:return task.result()
            if on_wait:on_wait(round(asyncio.get_running_loop().time()-start),seconds)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)

def interruption_report(evidence,run_id,reason,checkpoint=None):
    own=[e for e in evidence if e.get('run_id')==run_id]
    if checkpoint:
        report=deepcopy(checkpoint)
        report['summary']='本轮中断，以下为已保存阶段稿：'+report['summary']
        report['gaps']=list(dict.fromkeys([*report.get('gaps',[]),reason,'阶段稿未完成最终复核，不代表已验证推荐。']))
        return report
    return {'summary':f'本轮未完成：{reason}。本轮已归档{len(own)}项资料，保留供后续核对；未据此生成性能预测。',
            'findings':[], 'gaps':[reason,'需要基于已归档原文完成对照数据提取、模型适用性和目标方案核验。'],
            'proposed_tasks':[], 'formulations':[], 'processes':[], 'dissolution_curves':[]}


def model_wait_seconds(model_name, *, recovery=False):
    """Bound GLM long tool/report requests without the former 120s cutoff."""
    if model_name.startswith('openai:glm-'):return 300
    if not recovery and model_name in ('openai:gpt-6-astra','gpt-6-astra'):return 600
    return 180 if recovery else 120
