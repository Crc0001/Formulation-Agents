import React from 'react';
import SavedCurveDiagnostics from './SavedCurveDiagnostics';
export default function DoeResultSummary({base,selected,run,evidence}:{base:any;selected:any;run:any;evidence:any[]}){
 if(!selected||!run?.report)return null;
 const p=run.report.screening_progress,j=p?.judgment;
 const changed=(selected.ingredients??[]).flatMap((m:any)=>{const old=base?.ingredients?.find((x:any)=>x.id===m.id);return old&&old.amount_mg!==m.amount_mg?[{...m,before:old.amount_mg}]:[]});
 const ids=new Set([...(p?.calculation_evidence_ids??[]),...(p?.reasoning_chain?.calculation_ids??[])]);
 const computed=evidence.filter(e=>ids.has(e.id)&&e.basis==='hypothesis'&&['source_curve_model_json','source_response_model_json','pair_difference_model_json','source_metric_json'].some(k=>e.fields?.[k]));
 return <section style={{border:'2px solid #93c5fd',padding:18,borderRadius:10}}><h2>04 本次研究结果：先看这里</h2><p>已保存方案：{selected.title} · 报告时间：{new Date(run.created_at).toLocaleString()}。下方编辑草稿不会改变这份报告。</p>
 <h3>1. 本次改变</h3>{changed.length?<table><thead><tr><th>物料</th><th>基准 → 调整（mg）</th><th>差额（mg）</th></tr></thead><tbody>{changed.map((m:any)=><tr key={m.id}><td>{m.name}</td><td>{m.before??'未知'} → {m.amount_mg??'未知'}</td><td>{Number.isFinite(m.before)&&Number.isFinite(m.amount_mg)?(m.amount_mg-m.before).toFixed(2):'未知'}</td></tr>)}</tbody></table>:<p>两方案没有已识别的用量差异；品牌、规格和工艺另行核对。</p>}
 <h3>2. 智能体优先判断（待验证）</h3><p><strong>{j?.expected_pattern??p?.direction_reason??'本轮尚未交付方向判断。'}</strong></p><p>{j?.preferred_hypothesis}</p><p>依据：{j?.rationale??'尚未交付'}</p><details><summary>什么情况会推翻这个判断</summary><p>{j?.counterevidence}</p><p>成立条件：{j?.assumptions}</p><p>推翻条件：{j?.falsifier}</p></details>
 <h3>3. 已经算到哪里</h3><p>当前程序复核：{run.screening_audit?.issues?.length ? `仍有 ${run.screening_audit.issues.length} 项待解决，详见下方当前审计。历史报告中的附件缺失说明保留，不代表当前附件仍缺失。` : "引用检查通过不等于目标预测已验证。"}</p><p>本轮引用中找到 {computed.length} 份已保存的来源曲线、响应模型、配对差值或指标计算记录。记录存在不等于已验证当前处方；以下保留原始身份。</p><details><summary>查看已识别的来源计算</summary>{computed.map(e=><p key={e.id}>{e.title}</p>)}</details><p>目标计算状态：{p?.reasoning_chain?.transfer_reason??'尚未交付目标迁移判断'}。方向假设不表示已经算出改善幅度。</p>
 <SavedCurveDiagnostics evidence={computed}/>
 <h3>4. 报告记录的下一步</h3><p>{j?.next_program_action??p?.next_action??'尚未交付具体下一步。'}</p><p>若上方已有对应拟合诊断，应先解读已保存结果；历史“恢复附件”任务不表示数据丢失。公式、来源图与详细研究档案保留在下方。</p></section>;
}
