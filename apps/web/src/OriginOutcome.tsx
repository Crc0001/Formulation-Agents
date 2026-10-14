import React from 'react';
import {originRunStage} from './origin-stage-view';

export default function OriginOutcome({snapshot}:{snapshot:any}){
 const runs=[...(snapshot.origin?.runs??[])].sort((a:any,b:any)=>String(b.created_at).localeCompare(String(a.created_at)));
 const evidence=snapshot.origin?.evidence??[];
 const reports=runs.filter((r:any)=>r.report);
 const latest=reports[0],third=reports.find((r:any)=>originRunStage(r.message??'')===3);
 const report=latest?.report;
 const rows=report?.decision_comparison?.rows??[];
 const rec=third?.report?.origin_recommendation;
 const next=report?.decision_comparison?.next_steps??[];
 const gaps=[...new Set<string>([...(report?.gaps??[]),...(report?.decision_comparison?.limitations??[])])];
 const labels=['中国参比目录批次及序号','目标原研与版本','说明书辅料组成','辅料种类匹配','原研专利归属及时间关联','对应溶出证据','对应剂型质量与性能证据'];
 const resolve=(id:string)=>{const exact=evidence.find((e:any)=>e.id===id);if(exact)return exact;const matches=evidence.filter((e:any)=>e.id.startsWith(id));return matches.length===1?matches[0]:null};
 const links=(ids:string[])=>(ids??[]).map(id=>{const e=resolve(id);return e?.source_url?<a key={id} href={e.source_url} target="_blank" rel="noreferrer" style={{display:'block'}}>{e.title}</a>:<span key={id} style={{display:'block'}}>引用待核对：{id}</span>});
 return <section aria-label="当前成果与使用范围" style={{border:'1px solid #087e8b',padding:16,marginBottom:16}}>
 <h4>当前成果与使用范围</h4>
 <p>已归档 {evidence.length} 条资料记录（可能含同一文献的网页、图片及摘录，不能等同于独立文献篇数）。</p>
 {!report?<p>尚无研究报告，目前只能查看已存资料。</p>:<>
 <p>以下依据 {new Date(latest.created_at).toLocaleString()} 启动的最近已保存报告；展示报告判断，不自动升级为原文核验通过。</p>
 <h5>1. 已取得的研究结论与核对状态</h5>
 {rows.length?<div style={{overflowX:'auto'}}><table><thead><tr><th>研究问题</th><th>报告具体结论（含未核实项）</th><th>依据</th></tr></thead><tbody>{[...rows].sort((a:any,b:any)=>(labels.indexOf(a.metric)<0?99:labels.indexOf(a.metric))-(labels.indexOf(b.metric)<0?99:labels.indexOf(b.metric))).map((r:any,i:number)=><tr key={i}><td>{r.metric}</td><td>{r.values.map((v:string,j:number)=><p key={j}>{v}</p>)}{r.note&&<p className="muted">{r.note}</p>}</td><td>{links(r.source_ids)}</td></tr>)}</tbody></table></div>:<p>{report.summary||'尚未交付结构化结论，需继续整理已存资料。'}</p>}
 <h5>2. 目前可以用于什么</h5>
 {third?<><p>{third.report.decision_comparison?.recommendation||'第三阶段尚未给出明确使用建议。'}</p>{rec&&<><p><strong>报告提出的候选：</strong>{rec.formula_title}</p><p>{rec.rationale}</p>{rec.limitations?.map((v:string,i:number)=><p key={i}>候选限制：{v}</p>)}</>}</>:<p>尚未交付第三阶段的试验参考建议，目前用于资料核对，不能据此认定已有可采用处方。</p>}
 {third&&third.id!==latest.id&&<p>上述使用建议来自较早的第三阶段报告；最新补查成果尚需重新比较，旧建议不自动更新。</p>}
 <h5>3. 仍需核对或补齐</h5>
 {gaps.length?<ul>{gaps.map((g,i)=><li key={i}>{g}</li>)}</ul>:<p>本报告未列具体缺口；这不等于全部核验通过，可查看下方来源及阶段记录。</p>}
 <h5>4. 下一步补查</h5>
 {next.length?<ol>{next.map((n:string,i:number)=><li key={i}>{n}</li>)}</ol>:<p>报告未单列下一步，请依据上述缺口开展定向补查。</p>}
 </>}
 {runs.filter((r:any)=>['running','queued'].includes(r.status)||r.error).slice(0,3).map((r:any)=><p key={r.id} role="status">{new Date(r.created_at).toLocaleString()}：{r.error||'新一轮研究尚在运行，以上为此前已保存成果。'}</p>)}
 <details><summary>查看已归档资料清单（{evidence.length}条）</summary>{evidence.map((e:any)=><p key={e.id}>{links([e.id])}{e.basis==='image_estimate'?'图片/OCR提取，需核对原图':e.access||'读取范围见原资料'} · {e.locator||'未记录定位'}</p>)}</details>
 </section>;
}
