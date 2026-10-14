import React,{useState} from 'react';
export default function ExperimentFeedback({snap,baselineId,onSync}:{snap:any;baselineId:string;onSync:()=>Promise<void>}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const items=(snap.experiment_feedback??[]).filter((x:any)=>x.baseline_id===baselineId);
 const pending=(snap.anchors??[]).filter((x:any)=>x.variant_snapshot?.baseline_id===baselineId&&!items.some((r:any)=>r.anchor_id===x.id));
 return <section><h2>04 → 03 实测回传与模型复核</h2><p>在04保存实测结果后自动回传。进入03选择同一冻结基准，点击本专题“继续研究”，即可将结果带入复核；新结论与模型另存，原预测保留。</p>
 {pending.length>0&&<button disabled={busy} onClick={async()=>{setBusy(true);setError('');try{await onSync()}catch(e){setError(String(e))}finally{setBusy(false)}}}>补接历史实测（{pending.length}条）</button>}{error&&<p role="alert">{error}</p>}
 {!items.length&&<p>当前基准尚无实测回传。文献曲线和模拟结果不会自动记为实验。</p>}
 {items.map((x:any)=>{const uses=(snap.feedback_uses??[]).filter((u:any)=>u.feedback_ids.includes(x.id));return <details key={x.id}><summary>{x.batch} · {x.variant_snapshot.title} · {x.observed_points.length}个实测点 · {uses.length?'已交付03研究，复核结论见对应报告':'已回传，待03研究复核'}</summary><p>方法：{x.method}</p><p>回传ID：{x.id}；原记录：{x.anchor_id}</p><p>{x.prior_prediction?'已保留实验前预测版本：'+x.prior_prediction.id:'未绑定实验前预测，不能计算事前预测误差。'}</p><table><thead><tr><th>时间/min</th><th>实测溶出/%</th></tr></thead><tbody>{x.observed_points.map((p:number[],i:number)=><tr key={i}><td>{p[0]}</td><td>{p[1]}</td></tr>)}</tbody></table><p>04局部拟合：{x.local_fit.status}。该拟合不是03模型已校准的证明。</p>{uses.map((u:any)=><p key={u.id}>接收研究：{u.run_id} · {u.meaning}</p>)}</details>})}</section>
}
