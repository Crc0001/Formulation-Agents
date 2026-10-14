import BatchTransferPanel from './BatchTransferPanel';
import OriginRunStatus from './OriginRunStatus';
import OriginOutcome from './OriginOutcome';
import React,{useEffect,useState} from 'react';

export default function RecentReferenceDrugs({modelProfile}:{modelProfile:string}){
 const [queue,setQueue]=useState<any>(null),[batchBusy,setBatchBusy]=useState(false);
 const [batch,setBatch]=useState(108),[batches,setBatches]=useState<any[]>([]);
 const batchTitle=(s:any)=>`第${s.document_batch}批 · 发布${s.publication_date||'日期待核'}`;
 const [starting,setStarting]=useState(''),[notice,setNotice]=useState('');
 const [open,setOpen]=useState(false),[source,setSource]=useState<any>(null),[groups,setGroups]=useState<any[]>([]),[projects,setProjects]=useState<any[]>([]),[selected,setSelected]=useState(''),[snapshot,setSnapshot]=useState<any>(null),[error,setError]=useState('');
 useEffect(()=>{if(!open)return;let live=true;
  async function load(){try{
   const get=async(url:string)=>{const r=await fetch(url);if(!r.ok)throw Error('资料读取失败，请稍后重试');return r.json()};
   const [b,p]=await Promise.all([get('/api/origin-registry/batches'),get('/api/projects')]);
   const available=b.sources.filter((x:any)=>x.document_batch&&x.sha256&&x.parsed&&!/征求意见|调出/.test(x.document_title||x.title||'')).sort((a:any,b:any)=>b.document_batch-a.document_batch);
   const unique=available.filter((x:any,i:number)=>available.findIndex((y:any)=>y.document_batch===x.document_batch)===i);
   const s=unique.find((x:any)=>x.document_batch===batch)||unique[0];
   if(live)setBatches(unique);
   if(!s){if(live)setError('尚未取得可展示的正式批次原表');return}
   const d=await get('/api/origin-registry/rows?q='+encodeURIComponent(s.sha256));
   const grouped=new Map<string,any>();const seen=new Set<string>();
   for(const row of d.rows){if(row.source_sha256!==s.sha256||seen.has(row.entry_number))continue;seen.add(row.entry_number);const c=row.cells;if(c?.length!==7)continue;
    const key=JSON.stringify([c[1],c[2],c[4]]);if(!grouped.has(key))grouped.set(key,{name:c[1],english:c[2],holder:c[4],rows:[]});grouped.get(key).rows.push(row);
   }
   if(live){setSource(s);setGroups([...grouped.values()]);setProjects(p);setError('')}
  }catch(e){if(live)setError(String(e))}}
  load();const timer=setInterval(load,30000);return()=>{live=false;clearInterval(timer)};
 },[open,batch]);
 useEffect(()=>{setSnapshot(null);if(!selected)return;let live=true;
  async function load(){try{const r=await fetch('/api/projects/'+encodeURIComponent(selected));if(!r.ok)throw Error('研究详情读取失败');const s=await r.json();if(live)setSnapshot(s)}catch(e){if(live)setError(String(e))}}
  load();const timer=setInterval(load,5000);return()=>{live=false;clearInterval(timer)};
 },[selected]);
 useEffect(()=>{if(!open||!source)return;let live=true;setQueue(null);
  const load=async()=>{try{const r=await fetch(`/api/origin-registry/batches/${source.document_batch}/research`);if(!r.ok)throw Error('批量队列状态暂不可用');const d=await r.json();if(live)setQueue(d)}catch(e){if(live)setError(String(e))}};
  load();const timer=setInterval(load,5000);return()=>{live=false;clearInterval(timer)};
 },[open,source?.document_batch]);
 async function controlBatch(pause=false){if(batchBusy||!source)return;setBatchBusy(true);setError('');try{
  const r=await fetch(`/api/origin-registry/batches/${source.document_batch}/research${pause?'/pause':'?model_profile='+encodeURIComponent(modelProfile)}`,{method:'POST'});const d=await r.json();if(!r.ok)throw Error(d.detail||'提交失败');setQueue(d);
 }catch(e){setError(String(e))}finally{setBatchBusy(false)}}
 async function startGroup(g:any){
  if(starting)return;setStarting(g.rows[0].entry_number);setError('');setNotice('正在建立档案并提交研究…');
  try{
   const request=async(url:string,body?:any)=>{const r=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:undefined);const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'提交失败，请检查服务');return d};
   const name=`第${source.document_batch}批原研库 · ${g.name} · ${g.rows[0].entry_number}`;
   let all=await request('/api/projects');let p=all.find((p:any)=>p.name===name);
   if(!p){p=await request('/api/projects',{name,api:g.name,market:'中国参比及对应原研上市地区',strength:g.rows.map((r:any)=>r.cells[3]).join('；'),strength_basis:'目录原文规格，未作盐或活性换算',dosage_form:g.name+'（剂型按目录原文）'});all=[...all,p]}
   setProjects(all);setSelected(p.id);
   const result=await request(`/api/projects/${p.id}/origin-autostart?model_profile=${encodeURIComponent(modelProfile)}`,{});
   setNotice(result.message||'该品种已在研究中，请查看下方进度。');
   setSnapshot(await request('/api/projects/'+p.id));
   document.getElementById('recent-reference-detail')?.scrollIntoView({behavior:'smooth'});
  }catch(e){setError(String(e));setNotice('档案和已保存成果会保留，可重试提交。')}finally{setStarting('')}
 }
 const status=(s:string)=>({running:'研究中',queued:'已排队',completed:'本轮已交付',partial:'已交付部分成果',failed:'研究中断',cancelled:'已停止'}[s]||s);
 return <section style={{margin:'20px 0',padding:20,border:'2px solid #087e8b',borderRadius:12,background:'#eef8f8'}} aria-label="最近公布参比制剂的仿制药">
  <h3 style={{marginTop:0}}>参比制剂分批原研信息库</h3>
  <p>按最近收录的正式参比目录，查看相关品种的原研身份、说明书、专利、处方与工艺研究。</p>
  <BatchTransferPanel batch={batch} batches={batches}/>
  <button onClick={()=>setOpen(!open)} aria-expanded={open}>{open?'收起品种目录':'点击查看各批次品种与研究资料'}</button>
  {open&&<>{notice&&<p role="status">{notice}</p>}{error&&<p role="alert">{error}</p>}{!source&&!error&&<p>正在读取品种目录…</p>}{source&&<>
   <label>选择批次与发布时间 <select value={source.document_batch} onChange={e=>{setBatch(Number(e.target.value));setSource(null);setGroups([]);setSelected('');setSnapshot(null);setNotice('')}}>{batches.map(s=><option key={s.document_batch} value={s.document_batch}>{batchTitle(s)}</option>)}</select></label>
   <h4>{batchTitle(source)} · {groups.reduce((n,g)=>n+g.rows.length,0)}条目录记录 · {groups.length}个产品组</h4>
   <div style={{padding:16,background:'white',border:'2px solid #087e8b',borderRadius:8}}>
    <strong>本批批量研究</strong><p>一键逐品种完成身份说明书 → 专利处方工艺 → 比较推荐。已有任务和成果自动接续；单次研究失败保留资料，不反复重跑。</p>
    <button disabled={batchBusy||queue?.enabled} onClick={()=>controlBatch()}>{batchBusy?'正在提交…':queue?.enabled?'整批队列已启动':'开始／接续本批研究'}</button>
    {queue?.enabled&&<button disabled={batchBusy} onClick={()=>controlBatch(true)}>停止后续派单</button>}
    {queue&&<><p role="status">{queue.status} · 三阶段已交付 {queue.completed}/{queue.total} 组 · 尚未交付 {queue.total-queue.completed} 组</p>
     <p>执行进度与科学核验分别显示。待接续、超时或接口故障不代表必须人工研究；科学核验尚未完成也不等于程序运行失败。</p>
     {queue.current.map((x:any)=><p key={x.project_id}>正在研究：{x.name} · 阶段{x.phase} <a href={'/?project='+x.project_id}>查看进度</a></p>)}
     <details open><summary>逐品种执行状态与原因</summary><div style={{overflowX:'auto'}}><table><thead><tr><th>品种</th><th>阶段／执行状态</th><th>具体原因与进度</th><th>科学核验</th></tr></thead><tbody>
      {(queue.items||[]).map((x:any)=><tr key={x.project_id||x.name}><td><a href={'/?project='+x.project_id}>{x.name}</a></td><td>阶段{x.phase||'—'} · {x.label}</td><td>{x.reason}{x.pending_chunks>0&&<p>尚有 {x.pending_chunks} 段归档原文待整理</p>}</td><td>{x.scientific_status}</td></tr>)}
     </tbody></table></div></details></>}

    <small>停止后续派单会让当前品种的本轮研究完成。已交付不等于全部事实已核实。</small>
   </div>
   <p>包括本批新增及旧条目变更；同产品的不同规格分别保留。目录公布不等于对应仿制药已获批上市。这里可切换已收录正式批次，官方查新状态见下方。</p>
   {source.publication_date_source&&<p><a href={source.publication_date_source} target="_blank" rel="noreferrer">发布日期依据</a>：{source.publication_date_basis}</p>}
   <p><a href={source.url} target="_blank" rel="noreferrer">查看本批原表附件</a>（{source.authority==='official_attachment'?'官方附件':'归档来源副本'}；机器提取，待核对）</p>
   <div style={{overflowX:'auto'}}><table><thead><tr><th>品种／商品名</th><th>本批条目与规格</th><th>研究资料</th></tr></thead><tbody>{groups.map(g=>{
    const project=projects.find(p=>p.name===`第${source.document_batch}批原研库 · ${g.name} · ${g.rows[0].entry_number}`);
    return <tr key={g.rows[0].entry_number}><td><strong>{g.name}</strong><br/>{g.english}<details><summary>持有人</summary>{g.holder}</details></td><td>{g.rows.map((r:any)=><div key={r.entry_number}>{r.entry_number} · {r.cells[3]}{r.batch!==source.document_batch?'（历史条目变更）':''}</div>)}</td><td>{project?<><button onClick={()=>{setSelected(project.id);setTimeout(()=>document.getElementById("recent-reference-detail")?.scrollIntoView({behavior:"smooth",block:"start"}),0)}}>查看已有成果与进度</button><p><a href={`/?project=${encodeURIComponent(project.id)}`} target="_blank" rel="noreferrer">进入该品种01完整档案 ↗</a></p></>:<><p>尚未建立研究档案</p><button disabled={!!starting} onClick={()=>startGroup(g)}>{starting===g.rows[0].entry_number?'正在提交…':'建立档案并开始研究'}</button><p>自动依次研究身份、处方工艺和比较推荐；中断或关键资料不足时停下保留成果。</p></>}</td></tr>
   })}</tbody></table></div>
   {selected&&<section id="recent-reference-detail" style={{background:'white',padding:16,marginTop:16}} aria-live="polite"><h4>{snapshot?.project?.name||'正在读取研究详情…'}</h4>{snapshot&&<><OriginRunStatus snapshot={snapshot} onRefresh={async()=>{const r=await fetch('/api/projects/'+encodeURIComponent(selected));if(!r.ok)throw Error('状态更新失败');setSnapshot(await r.json())}}/><OriginOutcome snapshot={snapshot}/><details><summary>历次阶段报告与运行记录</summary>{snapshot.origin.runs.length===0?<p>尚未启动研究。</p>:snapshot.origin.runs.map((r:any)=><details key={r.id} open><summary>{r.message?.match(/【01阶段[123]】/)?.[0]||'01研究'} · {status(r.status)}</summary><p>{r.report?.summary||'本轮尚未交付报告；已有来源持续保存。'}</p>{r.report?.gaps?.length>0&&<details><summary>仍待解决：{r.report.gaps.length}项</summary><ul>{r.report.gaps.map((g:string,i:number)=><li key={i}>{g}</li>)}</ul></details>}</details>)}</details></>}</section>}
  </>}</>}
 </section>
}
