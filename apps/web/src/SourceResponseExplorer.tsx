import React,{useState} from 'react';
import {sourceResponse} from './sourceResponse';
import reviewed from '../../../reference/mcc-pgs-interactions-20260924/local-pdf-deep-review.json';
const fmt=(x:number)=>Number(x.toFixed(3));
export default function SourceResponseExplorer({source:s}:{source:any}){
 const [view,setView]=useState('surface'),[metric,setMetric]=useState('q15'),[mcc,setMcc]=useState(35);
 const strength=metric==='strength', model=strength?null:s.models[metric];
 const observed:number[]=strength?reviewed.observables.breaking_force_kp:s[metric];
 const label=strength?'破碎力 / kp':metric==='q15'?'Q15溶出率 / %':'崩解时间 / 秒';
 const calc=(p:number,m:number)=>sourceResponse(model.coefficients,p,m);
 const grid=model?Array.from({length:400},(_,i)=>{const p=5+(i%20+.5)/2,m=10+(Math.floor(i/20)+.5)*2.5;return {p,m,value:calc(p,m)}}):[];
 const values=grid.map(c=>c.value),low=model?Math.min(...values):0,high=model?Math.max(...values):1;
 const color=(v:number)=>`hsl(${210-(v-low)/(high-low||1)*170} 62% 55%)`;
 const rows=[0,1,2].map(i=>s.mcc_pct.findIndex((m:number,j:number)=>m===mcc&&s.pgs_pct[j]===[5,10,15][i]));
 const line=Array.from({length:41},(_,i)=>5+i/4);
 const lineValues=model?line.map(p=>calc(p,mcc)):rows.map(i=>observed[i]);
 const min=Math.min(...lineValues,...rows.map(i=>observed[i])),max=Math.max(...lineValues,...rows.map(i=>observed[i]));
 const pad=Math.max((max-min)*.18,.2),ymin=min-pad,ymax=max+pad;
 const px=(p:number)=>65+(p-5)*33,py=(v:number)=>230-(v-ymin)/(ymax-ymin)*175;
 const range=[...observed,...(model?[...model.fitted,...model.loo_predictions,model.confirmation_observed,model.confirmation_prediction]:[])];
 const vmin=Math.min(...range)-1,vmax=Math.max(...range)+1,sp=(v:number)=>65+(v-vmin)/(vmax-vmin)*320,sy=(v:number)=>230-(v-vmin)/(vmax-vmin)*175;
 return <div className="source-explorer"><p className="callout">来源研究：西地那非 · 图中所有数值属于该研究，未迁移到诺氟沙星。</p>
 <label>查看来源图<select aria-label="查看来源图" value={view} onChange={e=>{setView(e.target.value);if(e.target.value!=='slice'&&strength)setMetric('q15')}}><option value="surface">双因素响应面（颜色图）</option><option value="slice">固定MCC的条件曲线</option><option value="validation">实测与模型复验</option></select></label>
 <label>来源响应指标<select aria-label="来源响应指标" value={metric} onChange={e=>setMetric(e.target.value)}><option value="q15">15分钟溶出率 Q15</option><option value="dt_s">崩解时间</option>{view==='slice'&&<option value="strength">片剂破碎力（原表观察）</option>}</select></label>
 {view==='surface'&&model&&<><svg viewBox="0 0 480 340" role="img" aria-label={`西地那非${label}双因素响应面`}>
 {grid.map((c,i)=><rect key={i} x={65+i%20*16.5} y={240-(Math.floor(i/20)+1)*9} width="16.6" height="9.1" fill={color(c.value)}><title>PGS {c.p}% · MCC {c.m}% · 模型 {fmt(c.value)}</title></rect>)}
 {s.pgs_pct.map((p:number,i:number)=><circle key={i} cx={px(p)} cy={240-(s.mcc_pct[i]-10)*3.6} r="4" fill="white" stroke="#173b48"><title>F{i+1}：PGS{p}% / MCC{s.mcc_pct[i]}% · 原表{observed[i]} · 拟合{fmt(model.fitted[i])}</title></circle>)}
 <path d="M65 52V240H402" fill="none" stroke="#173b48"/>{[5,10,15].map(p=><text key={p} x={px(p)-5} y="262">{p}</text>)}{[10,35,60].map(m=><text key={m} x="34" y={244-(m-10)*3.6}>{m}</text>)}<text x="65" y="25">纵轴：MCC质量百分数</text><text x="160" y="284">横轴：PGS质量百分数</text>
 {Array.from({length:80},(_,i)=><rect key={i} x={65+i*4.1} y="300" width="4.2" height="12" fill={color(low+(high-low)*i/79)}/>)}<text x="65" y="332">{fmt(low)}</text><text x="340" y="332">{fmt(high)}</text></svg><p>{label}；白点为九个实际设计位置，颜色为二次模型的区间内计算。色带范围随指标变化，不表示概率或置信度。</p></>}
 {view==='slice'&&<><label>固定MCC含量<select aria-label="固定MCC含量" value={mcc} onChange={e=>setMcc(Number(e.target.value))}>{[10,35,60].map(m=><option key={m} value={m}>{m}%</option>)}</select></label><svg viewBox="0 0 480 300" role="img" aria-label={`西地那非固定MCC${mcc}%的${label}条件曲线`}><path d="M65 40V230H405" fill="none" stroke="#789"/>{[ymin,(ymin+ymax)/2,ymax].map(v=><g key={v}><text x="5" y={py(v)+4}>{fmt(v)}</text><path d={`M65 ${py(v)}H405`} stroke="#ddd"/></g>)}<polyline points={(model?line:[5,10,15]).map((p,i)=>`${px(p)},${py(lineValues[i])}`).join(' ')} fill="none" stroke="#bd5f35" strokeWidth="3"/>{rows.map(i=><g key={i}><circle cx={px(s.pgs_pct[i])} cy={py(observed[i])} r="5" fill="#087e8b"/><text x={px(s.pgs_pct[i])-15} y={py(observed[i])-12}>{observed[i]}</text></g>)}{[5,10,15].map(p=><text key={p} x={px(p)} y="252">{p}</text>)}<text x="65" y="25">{label}</text><text x="130" y="282">PGS质量百分数；甘露醇补差</text></svg><p>蓝点：来源均值。橙线：{model?'二次模型的条件截面，曲线不强制单调。':'仅连接三个原表观察点，未建立破碎力预测模型。'}</p><table><thead><tr><th>PGS%</th><th>实测均值</th><th>{model?'模型计算':'指标单位'}</th></tr></thead><tbody>{rows.map(i=><tr key={i}><td>{s.pgs_pct[i]}</td><td>{observed[i]}</td><td>{model?fmt(model.fitted[i]):'kp'}</td></tr>)}</tbody></table></>}
 {view==='validation'&&model&&<><svg viewBox="0 0 480 290" role="img" aria-label={`西地那非${label}实测与模型留出复验`}><path d="M65 40V230H405" fill="none" stroke="#789"/><path d={`M${sp(vmin)} ${sy(vmin)}L${sp(vmax)} ${sy(vmax)}`} stroke="#aaa" strokeDasharray="5 4"/>{observed.map((v,i)=><g key={i}><circle cx={sp(v)} cy={sy(model.fitted[i])} r="4" fill="#087e8b"><title>F{i+1} 实测{v} 拟合{fmt(model.fitted[i])}</title></circle><circle cx={sp(v)} cy={sy(model.loo_predictions[i])} r="4" fill="none" stroke="#bd5f35"><title>F{i+1} 整处方留出计算{fmt(model.loo_predictions[i])}</title></circle></g>)}<rect x={sp(model.confirmation_observed)-5} y={sy(model.confirmation_prediction)-5} width="10" height="10" fill="#8057ac"><title>确认处方：实测{model.confirmation_observed} 计算{fmt(model.confirmation_prediction)}</title></rect>{[vmin,(vmin+vmax)/2,vmax].map(v=><g key={v}><text x={sp(v)-10} y="253">{fmt(v)}</text><text x="5" y={sy(v)+4}>{fmt(v)}</text></g>)}<text x="65" y="25">纵轴：计算值</text><text x="110" y="280">横轴：来源实测值（{label}）</text></svg><p>蓝点：九处方拟合；橙圈：每次留出完整一个处方；紫方块：作者另做的确认处方；虚线：计算=实测。</p><p>拟合RMSE {fmt(model.rmse)}；留出RMSE {fmt(model.loo_rmse)}；确认偏差 {fmt(model.confirmation_error)}。单位：{metric==='q15'?'百分点':'秒'}。这是同研究复验，未证明跨药物迁移。</p></>}
 <p className="muted">固定西地那非及来源工艺、牌号和方法；PGS/MCC变化由甘露醇补差。响应面含组成共同变化，不能解释为各辅料独立贡献。</p></div>;
}
