import React,{useEffect,useState} from 'react';
import {originRunStage} from './origin-stage-view';
export default function OriginRunStatus({snapshot,onRefresh}:{snapshot:any;onRefresh:()=>Promise<void>}){
 const runs=[...(snapshot.origin?.runs??[])].sort((a:any,b:any)=>String(b.created_at).localeCompare(String(a.created_at)));
 const active=runs.find((r:any)=>['queued','running'].includes(r.status)),r=active??runs[0];
 const [events,setEvents]=useState<any[]>([]),[error,setError]=useState(''),[cancelling,setCancelling]=useState(false);
 useEffect(()=>{setEvents([]);setError('');if(!r)return;let live=true;
 const load=async()=>{try{const response=await fetch(`/api/origin/runs/${r.id}/events`);if(!response.ok)throw Error('进度读取失败');const d=await response.json();if(live){setEvents(d);setError('')}}catch(e){if(live)setError(String(e))}};
 load();const timer=setInterval(load,5000);return()=>{live=false;clearInterval(timer)}},[r?.id]);
 const cancel=async()=>{setCancelling(true);try{const response=await fetch(`/api/origin/runs/${r.id}/cancel`,{method:'POST'});if(!response.ok)throw Error('取消请求未成功');await onRefresh()}catch(e){setError(String(e))}finally{setCancelling(false)}};
 const labels:Record<string,string>={model_selected:'已选定模型',agent_started:'研究已启动',search_request:'检索资料',document_request:'读取原文',research_checkpoint:'保存阶段成果',origin_extract_progress:'提取处方工艺',origin_extract_saved:'保存提取结果',research_recovery:'尝试用已存资料恢复报告',model_error:'模型接口异常',provider_failure:'接口未恢复',run_status:'更新任务状态'};
 const reason=/RateLimit|429/i.test(r?.error??'')?'模型接口限流，本轮已停止。需检查所用模型的额度或频率限制后，再重新发起研究。':r?.error;
 return <section aria-label="本品种实时研究状态" style={{border:'2px solid '+(r?.error?'#b45309':'#087e8b'),padding:16,marginBottom:16,background:'#fff8ec'}}>
 <h4>本品种实时研究状态</h4><p><strong>{snapshot.project?.name}</strong></p>
 <p role="status">{r?({queued:'任务已排队',running:'正在研究',completed:'本轮运行结束',partial:'本轮已停止，交付部分成果',failed:'本轮失败，已停止',cancelled:'本轮已取消',interrupted:'本轮已中断'} as any)[r.status]??r.status:'尚未启动'}</p>
 {r&&<p>第{originRunStage(r.message??'')??'—'}阶段 · 启动时间：{new Date(r.created_at).toLocaleString()} · 已归档资料：{snapshot.origin.evidence.length}条</p>}
 {reason&&<p role="alert">停止原因：{reason}</p>}
 {active?<button disabled={cancelling} onClick={cancel}>{cancelling?'正在请求取消…':'取消本轮研究（保留已存资料）'}</button>:<p>当前没有运行中的任务，因此无需取消。已有成果保留在下方。</p>}
 {r&&!active&&<a href={`/?project=${encodeURIComponent(snapshot.project.id)}#origin-three-stages`} target="_blank" rel="noreferrer">进入该品种01档案，核对模型并定向补查 ↗</a>}
 <h5>最近进度</h5>{events.length?events.slice(-5).map((e:any,i:number)=><p key={i}>{new Date(e.created_at).toLocaleTimeString()} · {labels[e.kind]??'研究步骤'}{e.detail?.model?' · '+e.detail.model:''}{e.detail?.query?' · '+e.detail.query:''}{e.detail?.reason?' · '+e.detail.reason:''}</p>):<p>尚未读取到进度记录。</p>}
 {error&&<p role="alert">{error}；当前状态可能未及时更新。</p>}
 </section>
}
