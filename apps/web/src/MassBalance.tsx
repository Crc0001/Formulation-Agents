import React,{useState,useEffect} from 'react';
import {massTotal,balancePlan,MassItem} from './balance';
export default function MassBalance<T extends MassItem>({base,items,policy,apply}:{base:T[];items:T[];policy:string;apply:(items:T[])=>void}){
 const [id,setId]=useState('');
 const signature=JSON.stringify([base,items,policy]);
 useEffect(()=>setId(''),[signature]);
 const delta=massTotal(base)-massTotal(items),fmt=(n:number)=>Number(n.toFixed(6));
 const changed=items.filter(x=>x.amount_mg!==base.find(b=>b.id===x.id)?.amount_mg);
 let plan:ReturnType<typeof balancePlan<T>>|undefined,error='';
 if(id)try{plan=balancePlan(base,items,id)}catch(e){error=(e as Error).message}
 return <div className="callout"><strong>用量变化与补差</strong><p>基准总量 {fmt(massTotal(base))} mg → 当前 {fmt(massTotal(items))} mg；{Math.abs(delta)<1e-6?'总量一致':delta>0?'尚需增加 '+fmt(delta)+' mg':'尚需减少 '+fmt(-delta)+' mg'}。</p>
 {changed.length?changed.map(x=><p key={x.id}>{x.name}：{base.find(b=>b.id===x.id)?.amount_mg} → {x.amount_mg} mg</p>):<p>当前用量与基准相同；方案名称不会改变实际处方。</p>}
 {policy==='fixed'&&Math.abs(delta)>=1e-6&&<><label>由哪个辅料补差<select aria-label="补差辅料" value={id} onChange={e=>setId(e.target.value)}><option value="">请选择，不默认指定</option>{items.filter(x=>x.role==='excipient'&&!changed.some(c=>c.id===x.id)).map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label><p>列表保留尚未改量的辅料；也可直接在表格中手动补差。这里只计算质量差额，不代表该辅料药学上适合作为补差物料。</p>{plan&&<p>待应用：{items.find(x=>x.id===id)?.name} {plan.before} → {plan.after} mg；补差后总量 {fmt(massTotal(plan.items))} mg。</p>}{error&&<p role="alert">{error}</p>}<button type="button" disabled={!plan} onClick={()=>plan&&apply(plan.items)}>应用补差</button></>}
 {policy==='variable'&&<p>允许总量改变，不进行补差；保存后按上述实际用量研究。</p>}</div>
}
