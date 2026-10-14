import React,{useState} from 'react';
import {CurveOverview} from './TopicResponseDashboard';

export function changes(base:any,v:any){
 return (v.ingredients??[]).flatMap((m:any)=>{const b=base?.ingredients?.find((x:any)=>x.id===m.id);if(!b)return [];
 const fields=['amount_mg','brand','grade','particle'].filter(k=>b[k]!==m[k]);
 return fields.length?[{id:m.id,name:m.name,description:fields.map(k=>`${({amount_mg:'用量',brand:'品牌',grade:'规格',particle:'粒度'} as any)[k]}：${b[k]??'未知'} → ${m[k]??'未知'}${k==='amount_mg'?' mg':''}`).join('；')}]:[]});
}
export default function StudyNavigator({snap,base,selected,onBase,onSelect,onPrepare}:{snap:any;base:any;selected:any;onBase:(id:string)=>void;onSelect:(v:any)=>void;onPrepare:(q:string)=>void}){
 const [multi,setMulti]=useState(false),[factors,setFactors]=useState(''),[constraint,setConstraint]=useState(''),[response,setResponse]=useState('溶出曲线、崩解');
 const [sourceRun,setSourceRun]=useState('');
 const topics=new Map<string,any>();for(const binding of snap.interaction_runs??[]){const r=snap.interaction.runs.find((r:any)=>r.id===binding.run_id);if(!r?.report?.interaction_research)continue;const key=binding.baseline_id+JSON.stringify(binding.research_target);topics.set(key,{binding,run:r})}
 const source=snap.interaction.runs.find((r:any)=>r.id===sourceRun);
 const variants=snap.variants.filter((v:any)=>v.baseline_id===base?.id);
 const runIds=(v:any)=>(snap.excipient.runs??[]).filter((r:any)=>{try{return JSON.parse(r.message.split('\n变化方案：')[1].split('\n问题：')[0]).id===v.id}catch{return false}});
 return <section style={{border:'3px solid #087e8b',borderRadius:12,padding:20}} aria-label="处方与研究专题导航">
 <h2>04 · 先选处方，再选研究专题</h2><label>当前研究处方<select aria-label="当前研究处方" value={base?.id??''} onChange={e=>onBase(e.target.value)}><option value="">选择处方</option>{snap.baselines.map((b:any)=><option key={b.id} value={b.id}>V{b.version} · {b.title}</option>)}</select></label>
 <p>每张卡对应一个独立保存方案。选择后，下方判断、计算、运行历史及实测记录随方案切换；同一对物料的不同方案不会自动合并。</p>
 <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(270px,1fr))',gap:12}}>{variants.map((v:any)=>{const c=changes(base,v),rs=runIds(v);return <article key={v.id} style={{border:selected?.id===v.id?'3px solid #087e8b':'1px solid #cbd5e1',background:selected?.id===v.id?'#edf8fa':'white',padding:14,borderRadius:8}}><h3>{v.title}</h3>{c.map((m:any)=><p key={m.id}><strong>{m.name}</strong><br/>{m.description}</p>)}{!c.length&&<p>无已识别的物料变化；工艺和方法另行核对。</p>}<p>{v.total_policy==='fixed'?'固定总量；补差也属于本次变化':'允许总量变化'} · {rs.length}轮研究 · 方案{v.id.slice(0,8)}</p><button aria-pressed={selected?.id===v.id} onClick={()=>onSelect(v)}>{selected?.id===v.id?'当前专题：':'查看专题：'}{v.title}</button></article>})}</div>
 {!variants.length&&<p>本处方尚无保存方案。请在下方编辑用量、明确补差后保存，第一个专题就会出现在这里。</p>}
 {selected&&<p role="status"><strong>当前工作对象：{selected.title} · {selected.id.slice(0,8)}</strong>。以下研究使用这份保存方案。</p>}
 <p>两种辅料等量互换只有一个独立配比变量；识别两者各自效应及交互作用，需要可区分的因素设计。</p>
 <details><summary>本项目03研究专题（分别查看，不自动混入当前方案）</summary><div style={{display:'flex',gap:10,flexWrap:'wrap'}}>{[...topics.values()].map(({binding,run}:any)=>{const context=snap.baselines.find((b:any)=>b.id===binding.baseline_id)??snap.research_cases?.find((c:any)=>c.id===binding.baseline_id)?.context;const names=(binding.research_target?.material_ids??[]).map((id:string)=>context?.ingredients?.find((m:any)=>m.id===id)?.name??id);return <button key={run.id} aria-pressed={sourceRun===run.id} onClick={()=>setSourceRun(run.id)}>{names.join('—')} · {binding.baseline_id===base?.id?'当前处方专题':'独立案例 / 其他基准'} · {run.id.slice(0,8)}</button>})}</div>{source&&<article><h3>单独查看03专题：{source.report.interaction_research.source_case?.name}</h3><p>{source.report.interaction_research.pair_synthesis?.main_hypothesis}</p><p>{source.report.interaction_research.source_case?.target_transfer}</p><CurveOverview run={source} evidence={snap.interaction.evidence}/><details><summary>该专题研究目标与各指标观察</summary><p>{source.report.interaction_research.objective}</p>{source.report.interaction_research.studies?.map((s:any,i:number)=><p key={i}>{s.response}：{s.observed_relation}</p>)}</details><p>03来源模型单独展示；04仍使用上方选中的保存方案，未自动迁移参数。</p></article>}</details>
 <button onClick={()=>setMulti(!multi)} aria-expanded={multi}>多因素研究设计入口</button>
 {multi&&<div><h3>准备多因素研究任务</h3><p>可填写用量、品牌规格及工艺因素。此入口将要求带入研究问题供核对，尚不生成试验矩阵或启动实验。</p><label>因素及拟研究水平（每行一项）<textarea aria-label="多因素及水平" value={factors} onChange={e=>setFactors(e.target.value)} placeholder="例如：HPC用量及范围；NS-300用量及范围；制粒水量及范围"/></label><label>总量约束、补差物料及固定条件<textarea value={constraint} onChange={e=>setConstraint(e.target.value)}/></label><label>响应指标<input value={response} onChange={e=>setResponse(e.target.value)}/></label><button disabled={!base||!factors.trim()||!constraint.trim()||!response.trim()} onClick={()=>onPrepare(`针对冻结处方 ${base.title}（${base.id}）准备多因素研究设计。\n因素与水平：\n${factors}\n约束和固定条件：${constraint}\n响应：${response}\n先判断独立因素、补差混杂和设计可辨识性，选择混料设计、析因设计或响应面；复用03已存模型并列出需03补齐的关系。不要把配比一个自由度当两个独立因素，不把多个来源系数直接相加。先交付有依据的设计建议，未执行实验。`)}>将多因素要求带入研究问题</button></div>}
 </section>
}
