import React,{useState} from 'react';

export default function ContinueTopicResearch({run,disabled,onStart}:{run:any;disabled:boolean;onStart:(question:string)=>void}){
 const [metrics,setMetrics]=useState(['溶出','崩解']);
 const [extra,setExtra]=useState('');
 const [draft,setDraft]=useState('');
 const [review,setReview]=useState(false);
 const report=run.report?.interaction_research;
 const choices=[...new Set(['溶出','崩解','润湿与分散','硬度','脆碎度',...metrics])];
 const selected=[...new Set([...metrics,...extra.split(/[，,；;\n]/).map(s=>s.trim()).filter(Boolean)])];
 const gaps=[...new Set((report?.studies??[]).flatMap((s:any)=>s.confounders??[]))];
 const question=`继续本专题，重点响应：${selected.join('、')}。保留原冻结辅料、来源曲线和计算；已有成果作为起点，不从头重复研究。\n本轮待拆分的共变：${gaps.join('；')||'从已有研究逐项核对补差物料、工艺与规格共变'}。\n先盘点每项响应的已有数据及缺口，再定向检索同药、其它典型制剂或空白辅料的可比原始对照。优先寻找控制其它条件的单因素、多因素或混合设计，比较支持与反证，区分综合路径效应和独立贡献。按所选响应分别提取单位、方法、配方和工艺，调用程序计算有数据支撑的关系、误差和适用范围；无法识别系数时保留可检验假设，不把崩解、硬度代替溶出。优先复用已保存计算，不重复读同表或重新拟合同一组数据。逐项交付新增/修订/未解决的关系、来源图示及可给04使用的模型；新版本保存，旧成果保留，不改处方或实验记录。`;
 return <section aria-label="继续该专项研究">
  <h3>在已有成果上，继续辅料性能专项研究</h3>
  <p>目前已具备来源数据复算与图示的基本能力。继续研究将重点拆分辅料、补差及工艺的共同影响，逐步建立有依据的贡献关系。</p>
  <p><strong>本轮仍需区分：</strong>{gaps.join('；')||report?.pair_synthesis?.comparability||'见当前研究的适用条件与缺口。'}</p>
  <fieldset><legend>选择继续研究的性能指标（可多选）</legend>{choices.map(m=><label key={m} style={{display:'inline-flex',alignItems:'center',gap:6,marginRight:18}}><input style={{width:20,height:20}} type="checkbox" checked={metrics.includes(m)} onChange={e=>{setMetrics(e.target.checked?[...metrics,m]:metrics.filter(x=>x!==m));setReview(false)}}/>{m}</label>)}</fieldset>
  <label>增加其它指标（多个用逗号分隔）<input value={extra} placeholder="例如：吸水速率、抗张强度" onChange={e=>{setExtra(e.target.value);setReview(false)}}/></label>
  <p>本次选择：{selected.join('、')||'请选择或填写至少一个指标'}。沿用本轮专题和模型选择；启动后会产生新的研究记录。</p>
  {!review?<button disabled={disabled||!selected.length} onClick={()=>{setDraft(question);setReview(true)}}>准备继续该专项研究</button>:<><label>本次专项任务（可补充）<textarea rows={8} value={draft} onChange={e=>setDraft(e.target.value)}/></label><button disabled={disabled||!draft.trim()} onClick={()=>onStart(draft)}>启动继续该专项研究</button></>}
  {disabled&&<p>当前有任务执行或提交中，完成后可继续。</p>}
 </section>;
}
