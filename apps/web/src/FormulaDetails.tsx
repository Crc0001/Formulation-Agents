import React from 'react';
import {matchingProcesses} from './origin-linkage';
export {matchingProcesses} from './origin-linkage';

const roles:Record<string,string>={patent_example:'专利开发候选',official_label:'官方说明书',unknown:'来源身份待核'};
export function processDraft(formula:any,report:any){
 const processes=matchingProcesses(formula,report);
 const rec=report.origin_recommendation;
 const summary=rec?.formula_title===formula.title&&rec.process?'研究报告工艺概述（待核验，非已确认生产指令）：\n'+rec.process+'\n\n':'';
 if(!processes.length)return summary+'尚未取得与此候选关联的结构化工艺，需核对';
 return summary+'已归档的对应工艺，原文/OCR及数值冲突仍需核对：\n'+processes.map((p:any)=>`${p.title}（${p.applicability??'实施例对应关系需核对'}）\n${p.steps.map((s:any)=>`${s.order}. ${s.equipment?'设备：'+s.equipment+'；':''}${s.action_quote}${s.parameters?'；'+s.parameters:''}`).join('\n')}`).join('\n\n');
}
// Recover only literal source context. Never infer numeric settings or change stored steps.
export function sourceContext(quote:string,text:string,locator=''){
 const marker=locator.match(/\[\d{4}\]/)?.[0];
 if(marker){const at=text.indexOf(marker);if(at>=0&&text.indexOf(marker,at+1)<0){const next=text.slice(at+marker.length).search(/\[\d{4}\]/);text=text.slice(at,next<0?undefined:at+marker.length+next)}}
 const chars:number[]=[];let compact='';
 for(let i=0;i<text.length;i++)if(!/\s/.test(text[i])){compact+=text[i].toLowerCase();chars.push(i)}
 const q=quote.replace(/\s/g,'').toLowerCase();const at=compact.indexOf(q);
 if(!q||at<0||compact.indexOf(q,at+1)>=0)return '';
 const a=chars[at],b=chars[at+q.length-1]+1;
 const start=Math.max(text.lastIndexOf('；',a-1),text.lastIndexOf('。',a-1))+1;
 const end=/[；。]/.test(text[b-1])?-1:text.slice(b).search(/[；。]/);
 const fragment=text.slice(start,end<0?b:b+end+1).trim();
 return fragment.length<=1800?fragment:quote;
}
function Sources({ids,evidence}:{ids:string[];evidence:any[]}){return <>{ids.map(id=>{const e=evidence.find(x=>x.id===id);return e?<p key={id}><a href={e.source_url} target="_blank" rel="noreferrer">{e.title}</a><small>{e.locator} · {e.basis==='image_estimate'?'图片识别，尚未核验':'已归档来源'}</small></p>:<p key={id}>来源待核对</p>})}</>}
export default function FormulaDetails({report,evidence}:{report:any;evidence:any[]}){
 const formulas=report.formulations??[],processes=report.processes??[];
 if(!formulas.length&&!processes.length)return <p className="muted">本轮尚未交付处方组成或工艺步骤。</p>;
 return <section className="formula-details"><h3>处方组成与制备工艺</h3><p>以下保留来源的规格、批量和用量。不是自动换算后的目标处方；查看不代表采用。</p>
 {formulas.map((f:any,i:number)=><article key={i} className="source-formula"><h4>{f.title}{report.origin_recommendation?.formula_title===f.title?(f.components?.some((c:any)=>c.amount_mg!=null||c.batch_amount!=null||c.percent!=null)?' · 试验参考候选':' · 身份/组成依据'):''}</h4><p>{roles[f.source_role]??f.source_role} · {f.product} · {f.batch_units?`原文批量 ${f.batch_units} 个制剂单位`:'原文批量单位数未明确'}</p><p className="callout">{f.applicability}</p>{formulas.filter((x:any)=>x.title===f.title).length>1&&<p className="error">同名候选有多份来源或提取版本，须核对差异，不能按记录条数认定独立处方。</p>}
 <div style={{overflowX:'auto'}}><table aria-label={f.title+'处方组成'}><thead><tr><th>物料 / 部位</th><th>原文列量（单片/批量见依据）</th><th>每制剂单位 / mg</th><th>原文比例 / %</th><th>规格及依据</th></tr></thead><tbody>{f.components.map((c:any,j:number)=><tr key={j}><td>{c.name}<small>{c.compartment==='shell'?(f.dosage_form==='tablet'?'包衣物料（与片芯分开）':'壳/包衣（与内容物分开）'):c.compartment==='fill'?(f.dosage_form==='tablet'?'片芯':'内容物'):'部位待核'}</small></td><td>{c.source_amount!=null?`${c.source_amount} ${c.source_unit||'单位待核'}${c.source_quantity_basis?'；'+c.source_quantity_basis:''}`:c.batch_amount!=null?`${c.batch_amount} ${c.batch_mass_unit??'单位待核'}`:'未报告'}</td><td>{c.amount_mg??'未确定'}</td><td>{c.percent??'未报告'}</td><td>{c.grade||'规格未明确'}<small>{c.locator}</small></td></tr>)}</tbody></table></div><p>工艺关联：{matchingProcesses(f,report).map((p:any)=>p.title).join('；')||'尚未取得，不能沿用其他候选工艺'}</p><Sources ids={f.source_ids??[]} evidence={evidence}/></article>)}
 <h3>逐步制备工艺</h3>{!processes.length&&<p>本轮尚未交付可引用的工艺步骤。</p>}{processes.map((p:any,i:number)=><article className="source-formula" key={i}><h4>{p.title}</h4><p>{p.scope} · {p.applicability}</p><ol>{p.steps.map((s:any,j:number)=>{let context='';for(const id of p.source_ids??[]){const e=evidence.find(x=>x.id===id&&x.basis==='source');if(e){context=sourceContext(s.action_quote,e.text,s.locator);if(context)break}}return <li key={j}><strong>步骤 {s.order}{s.equipment?' · '+s.equipment:''}</strong><p>{s.action_quote}</p>{s.parameters&&<p>已记录条件：{s.parameters}</p>}{context&&context!==s.action_quote&&<blockquote><small>对应原文及相邻条件（未自动写入工艺参数）</small>{context}</blockquote>}{s.operation==='unknown'&&<small>结构化工艺标签或参数仍待核对；请以上方来源原文为依据。</small>}<small>{s.locator}</small></li>})}</ol><Sources ids={p.source_ids??[]} evidence={evidence}/></article>)}</section>;
}
