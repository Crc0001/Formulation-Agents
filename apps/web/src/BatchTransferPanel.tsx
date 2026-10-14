import React,{useEffect,useState} from 'react';
async function request(url:string,options?:RequestInit){const r=await fetch(url,options);const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'成果读取失败');return d}
export default function BatchTransferPanel({batch,batches}:{batch:number,batches:any[]}){
 const [mode,setMode]=useState(''),[chosen,setChosen]=useState(batch),[info,setInfo]=useState<any>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState<any>(null),[history,setHistory]=useState<any[]>([]),[available,setAvailable]=useState<any[]>([]);
 const refresh=()=>request('/api/origin-registry/imports').then(setHistory).catch(()=>{});
 useEffect(()=>{refresh();request('/api/origin-registry/batches').then(d=>setAvailable(d.sources.filter((s:any)=>s.document_batch&&!/征求意见|调出/.test(s.document_title||s.title||'')))).catch(()=>{})},[]);
 const options=batches.length?batches:available;
 useEffect(()=>{if(mode!=='export')return;let live=true;setInfo(null);setError('');setBusy(true);request(`/api/origin-registry/batches/${chosen}/export-preview`).then(x=>{if(live)setInfo(x)}).catch(e=>{if(live)setError(String(e.message))}).finally(()=>{if(live)setBusy(false)});return()=>{live=false}},[mode,chosen]);
 const open=(m:string)=>{setChosen(batch);setInfo(null);setResult(null);setError('');setMode(m)};
 async function upload(f:File){setBusy(true);setInfo(null);setResult(null);setError('');try{if(f.size>1024*1024*1024)throw Error('文件超过1GB');setInfo(await request('/api/origin-registry/import-preview',{method:'POST',headers:{'Content-Type':'application/zip'},body:f}))}catch(e){setError(String((e as Error).message))}finally{setBusy(false)}}
 async function apply(){setBusy(true);setError('');try{setResult(await request('/api/origin-registry/import/'+info.token,{method:'POST'}));refresh()}catch(e){setError(String((e as Error).message))}finally{setBusy(false)}}
 return <div style={{margin:'14px 0',padding:14,border:'1px solid #087e8b',borderRadius:8,background:'white'}}>
  <strong>跨电脑汇总批次成果</strong><p>另一台电脑导出成果包，在这里导入并合并。已有研究和原文保留。</p>
  <button onClick={()=>open('export')}>导出某批次成果</button> <button onClick={()=>open('import')}>导入成果</button>
  {!!history.length&&<details><summary>已导入成果（{history.length}个包）</summary>{history.map((h:any,i:number)=><div key={i}><strong>第{h.batch}批 · {h.products}个品种</strong>{h.projects?.map((p:any)=><p key={p.id}><a href={`/?project=${encodeURIComponent(p.id)}`}>{p.name}</a></p>)}</div>)}</details>}
  {mode&&<div style={{position:'fixed',inset:0,background:'#0007',zIndex:10000,display:'grid',placeItems:'center'}}><div role="dialog" aria-modal="true" aria-label={mode==='export'?'导出批次成果':'导入批次成果'} style={{background:'white',color:'#163342',padding:24,borderRadius:12,width:'min(640px,92vw)',maxHeight:'85vh',overflowY:'auto'}}>
   <h2>{mode==='export'?'导出某批次成果':'导入成果并合并'}</h2>
   {mode==='export'?<label>选择批次 <select value={chosen} onChange={e=>setChosen(Number(e.target.value))}>{[...new Set([batch,...options.map(b=>b.document_batch)])].sort((a,b)=>b-a).map(n=><option key={n} value={n}>第{n}批{options.find(b=>b.document_batch===n)?.publication_date?' · 发布'+options.find(b=>b.document_batch===n).publication_date:''}</option>)}</select></label>:<label>选择另一台电脑导出的ZIP成果包 <input type="file" accept=".zip" disabled={busy} onChange={e=>{const f=e.target.files?.[0];if(f)upload(f)}}/></label>}
   {busy&&<p role="status">正在处理，请稍候…</p>}{error&&<p role="alert" style={{color:'#b42318'}}>{error}</p>}
   {info&&<><h3>第{info.batch}批成果</h3><p>{info.products}个品种 · {info.reports}份报告 · {info.evidence}条资料 · {info.files}个原文附件</p><p>快照时间：{info.exported_at}</p>{info.active>0&&<p>包含{info.active}个未完成研究的当前资料；导入后不会自动启动任务。</p>}{info.missing_files>0&&<p style={{color:'#9b5100'}}>有{info.missing_files}个附件未在本机找到，包内会保留缺失标记；不代表原文齐全。</p>}
   <details><summary>查看品种清单</summary>{info.names.map((n:string,i:number)=><p key={i}>{n}</p>)}</details>
   {mode==='export'?<><p>包含01已存报告、资料和可取得的原文附件，不含接口密钥、处方采纳状态或执行队列。运行中的研究只导出下载时已有内容。</p><a href={`/api/origin-registry/batches/${chosen}/export`} download>下载第{chosen}批成果包</a></>:<><p>本机已有{info.existing}个品种；将新增{info.products-info.existing}个品种。已有品种追加外部版本，不覆盖原记录；不同结论请对照来源核查。</p><button disabled={busy||!!result} onClick={apply}>确认导入并合并</button></>}
   </>}
   {result&&<div role="status"><p>{result.duplicate?'此包已导入，没有重复添加。':`导入完成，新增${result.added_records}条资料或研究记录。`}</p>{result.projects.map((p:any)=><p key={p.id}><a href={`/?project=${encodeURIComponent(p.id)}`}>查看：{p.name}</a></p>)}</div>}
   <p><button disabled={busy} onClick={()=>setMode('')}>关闭</button></p>
  </div></div>}
 </div>
}
