import React from 'react';
const fmt=(x:number)=>x.toFixed(2);
export default function TopicEndpointResults({records,evidence}:{records:any[];evidence:any[]}){
 if(!records.length)return null;
 return <section><h3>主案例：已完成的配对性能比较</h3><p><strong>{records.reduce((n,r)=>n+r.pairs.length,0)}组来源端点差值已保存。</strong>下方按响应和条件分别展示。历史阶段报告中的“尚未计算”不代表这些已保存结果不存在。</p><p>蓝色＝前组，橙色＝后组，具体样品标签见每行。差值＝后组−前组；时间指标越小表示达到对应释放比例越早，不能据此判断整条曲线始终更快。</p>
 {records.map(r=>{const max=Math.max(...r.pairs.flatMap((p:any)=>[Math.abs(p.before),Math.abs(p.after)]),1);const source=evidence.find(e=>e.id===r.source_id);return <article key={r.id}><h4>{r.title}（{r.unit}）</h4><p>{r.metric_snapshot?.conditions}</p>
 {r.pairs.map((p:any,i:number)=><div key={i} style={{padding:12,border:'1px solid #cbd5e1',marginBottom:12,borderRadius:8}}><strong>{p.conditions}</strong><svg viewBox="0 0 680 112" style={{width:'100%',maxWidth:850}} role="img" aria-label={`${p.before_label} ${fmt(p.before)}，${p.after_label} ${fmt(p.after)} ${r.unit}，差值${fmt(p.difference)}`}>
 <text x="5" y="26" fontSize="14">{p.before_label}</text><rect x="115" y="10" width={450*Math.abs(p.before)/max} height="25" fill="#2563eb"/><text x={125+450*Math.abs(p.before)/max} y="28">{fmt(p.before)}</text>
 <text x="5" y="65" fontSize="14">{p.after_label}</text><rect x="115" y="49" width={450*Math.abs(p.after)/max} height="25" fill="#c2410c"/><text x={125+450*Math.abs(p.after)/max} y="67">{fmt(p.after)}</text><text x="115" y="100">柱长表示绝对值；数值保留正负号。单位：{r.unit}</text></svg>
 <p>后组−前组：<strong>{p.difference>0?'+':''}{fmt(p.difference)} {r.unit}</strong>{Number.isFinite(p.relative_change_percent)?`；相对前组 ${p.relative_change_percent>0?'+':''}${fmt(p.relative_change_percent)}%`:''}</p><details><summary>配对依据及样品身份</summary><p>{p.comparison_basis}</p><p>{p.basis_quote}</p>{r.metric_snapshot?.points?.filter((v:any)=>[p.before_label,p.after_label].includes(v.label)).map((v:any)=><p key={v.label}>{v.label}：{v.quote}</p>)}</details></div>)}
 <p>来源：{source?.source_url?<a href={source.source_url} target="_blank" rel="noreferrer">{source.title}</a>:r.source_id} · {r.metric_snapshot?.locator}</p><details><summary>适用范围及未解决项</summary>{r.limitations?.map((x:string,i:number)=><p key={i}>{x}</p>)}</details></article>})}
 <p><strong>可交付04：</strong>来源端点、条件差异和待验证假设。只有两个组成端点时，尚不能确定中间配比的连续关系；这些图不是当前项目的预测溶出曲线。</p></section>;
}
