import React,{useState} from 'react';
import {responseGroups,responseValue} from './response-explorer';
import {topicEndpoints} from './topic-endpoints';
import TopicEndpointResults from './TopicEndpointResults';
const fmt=(x:number|null)=>x==null?'不可估算':x.toFixed(2);
const label=(r:any)=>({'Q6':'6分钟溶出率','disintegration time':'崩解时间','reported hardness':'硬度（原文单位）','friability':'脆碎度','wetting time':'润湿时间','dispersion time':'宏观分散时间'} as any)[r.y_name]??r.y_name;
export function CurveOverview({evidence,run}:{evidence:any[];run:any}){
 const ids=new Set(run.report.interaction_research.source_case?.calculation_ids??[]);
 const records=evidence.flatMap(e=>{try{const r=JSON.parse(e.fields?.source_curve_model_json??'null');return ids.has(e.id)&&r?.arms?.length?[{...r,id:e.id}]:[]}catch{return []}});
 return <>{records.map(r=>{const machineRead=r.source_readings?.some((x:string)=>x.includes('机器复核'));const points=r.arms.flatMap((a:any)=>a.observed_points);const xmax=Math.max(...points.map((p:number[])=>p[0])),ymax=Math.max(100,...points.map((p:number[])=>p[1]));const px=(x:number)=>45+530*x/xmax,py=(y:number)=>225-195*y/ymax;const colors=['#087e8b','#c75b19','#8447b0','#334155'];return <article key={r.id}><h3>来源溶出曲线叠加比较</h3><p>{r.change}；{r.conditions}</p>{machineRead&&<p className="callout">数据来自印刷表格的视觉转录，两次机器读取一致；仍需原图复核。圆点为转录的文献报告值，虚线为来源拟合，不是本药预测。</p>}<svg viewBox="0 0 640 270" role="img" aria-label="来源各配方溶出原始点及Weibull拟合对比" style={{width:'100%'}}><path d="M45 20V225H580" fill="none" stroke="#64748b"/>{r.arms.map((a:any,i:number)=>{const m=a.models?.find((v:any)=>v.model==='weibull');return <g key={a.label}>{m&&<polyline points={m.fitted_points.map((p:number[])=>`${px(p[0])},${py(p[1])}`).join(' ')} fill="none" stroke={colors[i%4]} strokeDasharray="5 3" strokeWidth="2"/>}{a.observed_points.map((p:number[],j:number)=><circle key={j} cx={px(p[0])} cy={py(p[1])} r="4" fill={colors[i%4]}><title>{a.label}: {p[0]}分钟，{p[1]}%</title></circle>)}</g>})}<text x="0" y="30">{ymax}%</text><text x="20" y="225">0</text><text x="45" y="250">0</text><text x="490" y="250">{xmax} 分钟</text></svg>{r.arms.map((a:any,i:number)=><p key={a.label} style={{color:colors[i%4]}}>● {a.label}：圆点为{machineRead?'机器转录的文献报告值':'来源实测值'}{a.models?.some((m:any)=>m.model==='weibull')?'，同色虚线为Weibull拟合':'；本组未绘制Weibull拟合'}</p>)}<p>仅显示来源记录时间范围；不由Q6单点模型生成中间配比的整条溶出曲线。</p></article>})}</>;
}
export function Group({records,evidence}:{records:any[];evidence:any[]}){
 const first=records[0];const [x,setX]=useState(first.domain[0]);
 const source=evidence.find(e=>e.id===first.source_id);
 return <article><h3>{first.reviewedPandaSeries?'预胶化木豆淀粉—乳糖（F6–F9）':first.x_name}：来源范围内联动模拟</h3><p>{first.conditions}</p><p>组成约束：{first.x_basis}。滑块只改变本图情景，不修改项目处方。</p>{first.reviewedPandaSeries&&<p><strong>预胶化木豆淀粉 {fmt(x)} mg／乳糖 {fmt(95-x)} mg；两物料合计95 mg，整片200 mg。</strong></p>}
 <label>改变来源因素：{fmt(x)} {first.x_unit}<input aria-label={'来源模拟滑块 '+first.x_name} type="range" min={first.domain[0]} max={first.domain[1]} step={(first.domain[1]-first.domain[0])/100} value={x} onChange={e=>setX(Number(e.target.value))}/></label>
 <p>蓝点＝来源原始值；橙线＝已保存的经验模型；紫点及虚线＝当前滑块的模型估算。各图纵轴单位独立。</p>
 <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(290px,1fr))',gap:16}}>{records.map(r=>{
 const val=responseValue(r,x);const m=r.models.find((v:any)=>v.degree===r.selected_degree);
 const all=[...r.observed,...r.curve];const low=Math.min(...all.map((p:number[])=>p[1])),high=Math.max(...all.map((p:number[])=>p[1]));
 const px=(v:number)=>48+260*(v-r.domain[0])/(r.domain[1]-r.domain[0]);const py=(v:number)=>175-140*(v-low)/(high-low||1);
 return <div key={r.id}><h4>{label(r)}：{fmt(val)} {r.y_unit}</h4><svg viewBox="0 0 350 225" role="img" aria-label={`${label(r)} 来源原值与模型，当前估算${fmt(val)}${r.y_unit}`} style={{width:'100%'}}>
 <path d="M48 25V175H315" fill="none" stroke="#64748b"/>
 <polyline points={r.curve.map((p:number[])=>`${px(p[0])},${py(p[1])}`).join(' ')} fill="none" stroke="#c75b19" strokeWidth="2"/>
 {r.observed.map((p:number[],i:number)=><circle key={i} cx={px(p[0])} cy={py(p[1])} r="4" fill="#087e8b"><title>{p[0]}: {p[1]} {r.y_unit}</title></circle>)}
 {val!==null&&<><path d={`M${px(x)} 25V175`} stroke="#8447b0" strokeDasharray="4 3"/><circle cx={px(x)} cy={py(val)} r="6" fill="#8447b0"/></>}
 <text x="0" y="30">{fmt(high)}</text><text x="0" y="178">{fmt(low)}</text><text x="48" y="201">{r.domain[0]}</text><text x="285" y="201">{r.domain[1]}</text><text x="80" y="220">{r.x_unit} →　响应 {r.y_unit}</text></svg>
 <p>拟合误差 {fmt(m.rmse)}；内部留出误差 {fmt(m.internal_level_holdout_rmse)} {r.y_unit==='%'?'个百分点':r.y_unit}</p><p>检测条件：{r.conditions}</p>
 <details><summary>原始点、公式与残差</summary><p>{r.equation}；center={r.center}；scale={r.scale}；系数={m.coefficients.join(', ')}</p><table><thead><tr><th>因素/{r.x_unit}</th><th>来源/{r.y_unit}</th><th>拟合−来源</th></tr></thead><tbody>{r.observed.map((p:number[],i:number)=><tr key={i}><td>{p[0]}</td><td>{p[1]}</td><td>{fmt((responseValue(r,p[0])??NaN)-p[1])}</td></tr>)}</tbody></table><p>{r.confounders?.join('；')}</p><p>{r.limitations?.join('；')}</p></details></div>;
 })}</div><p>原始来源：{source?.source_url?<a href={source.source_url} target="_blank" rel="noreferrer">{source.title}</a>:first.source_id} · {first.locator}</p></article>;
}
export default function TopicResponseDashboard({evidence,run,onContinue,disabled}:{evidence:any[];run:any;onContinue:()=>void;disabled:boolean}){
 const groups=responseGroups(evidence,run);const endpoints=topicEndpoints(evidence,run);const curveIds=new Set(run.report?.interaction_research?.source_case?.calculation_ids??[]);const hasCurves=evidence.some(e=>curveIds.has(e.id)&&e.fields?.source_curve_model_json);if(!groups.length&&!endpoints.length&&!hasCurves)return null;
 const report=run.report.interaction_research;
 return <section><h2>本专题图形化成果与模拟</h2><h3>{report.source_case?.name}</h3><p>{report.pair_synthesis?.direct_exchange_status}</p><p><strong>待检验的机制假设：</strong>{report.pair_synthesis?.main_hypothesis}</p><button disabled={disabled} onClick={onContinue}>继续研究（使用新版程序，保留本轮成果）</button><p>沿用该轮冻结目标、原文和计算，补查曲线、非线性与机制分歧；新结果另存一轮。</p><TopicEndpointResults records={endpoints} evidence={evidence}/><CurveOverview evidence={evidence} run={run}/>{groups.length>0&&<h3>其它已归档来源响应模型（各自条件独立）</h3>}{groups.map(g=><Group key={g[0].id} records={g} evidence={evidence}/>)}<p>这是来源制剂条件内的模拟，误差不是置信区间；尚未成为当前药物预测。多指标同向或反向变化不等于独立因果贡献。</p></section>;
}
