import React,{useState} from 'react';
// Private measurements stay local; a source checkout must also work without them.
type LocalPairData={times:number[];method:string;rows:{id:string;mcc_pct:number;starch_pct:number;lactose_pct:number;q_pct:number[]}[]};
const localFiles=import.meta.glob<LocalPairData>('./mecobalamin-pair-data.json',{eager:true,import:'default'});
const data=localFiles['./mecobalamin-pair-data.json'];
export default function MecobalaminSlider({trend}:{trend:any}) {
 const [mcc,setMcc]=useState(30),[fraction,setFraction]=useState(.5);
 if(!data)return <section className="callout"><p>尚未导入本机私人实验数据，实测配比滑块暂不可用。</p></section>;
 const rows=data.rows.filter(r=>r.mcc_pct===mcc).sort((a,b)=>a.starch_pct-b.starch_pct);
 const first=rows[0],last=rows[rows.length-1],pct=first.starch_pct+fraction*(last.starch_pct-first.starch_pct);
 const index=rows.findIndex((r,i)=>i<rows.length-1&&pct<=rows[i+1].starch_pct);
 const low=rows[Math.max(0,index)],high=rows[Math.max(0,index)+1];
 const w=(pct-low.starch_pct)/(high.starch_pct-low.starch_pct);
 const q=low.q_pct.map((v,i)=>v+(high.q_pct[i]-v)*w),lactose=low.lactose_pct+(high.lactose_pct-low.lactose_pct)*w;
 const colors=['#087e8b','#8057ac','#cc643c'];
 const points=(qs:number[])=>qs.map((v,i)=>`${45+data.times[i]/30*410},${205-v*1.7}`).join(' ');
 return <section className="callout" aria-label="甲钴胺可调溶出曲线"><h4>拖动淀粉用量，查看甲钴胺溶出曲线变化</h4><p>你的实际研究处方内插；乳糖自动等量补差，90 mg片芯总量保持不变。仅预览，不改已保存处方。</p><label>固定微晶纤维素<select aria-label="实测系列微晶纤维素" value={mcc} onChange={e=>{setMcc(Number(e.target.value));setFraction(.5)}}>{[25,30,35].map(v=><option key={v} value={v}>{v}%片芯（{(v*.9).toFixed(1)} mg）</option>)}</select></label><label>玉米淀粉：{(pct*.9).toFixed(3)} mg（{pct.toFixed(2)}%片芯）<input type="range" aria-label="甲钴胺实测范围淀粉用量滑块" min="0" max="1" step="0.01" value={fraction} onChange={e=>setFraction(Number(e.target.value))}/></label><p>乳糖自动补差至 {(lactose*.9).toFixed(3)} mg；淀粉可调范围 {(first.starch_pct*.9).toFixed(3)}—{(last.starch_pct*.9).toFixed(3)} mg。原表比例有取整，换算为研究显示值。</p><svg viewBox="0 0 490 250" role="img" aria-label={`甲钴胺动态内插溶出曲线，淀粉${(pct*.9).toFixed(3)}毫克，30分钟${q[4].toFixed(2)}%`}><text x="5" y="15">溶出（%）</text>{[0,50,100].map(v=><g key={v}><path d={`M45 ${205-v*1.7}H460`} stroke="#ddd"/><text x="5" y={210-v*1.7}>{v}</text></g>)}{data.times.map(t=><text key={t} x={45+t/30*410-7} y="226">{t}</text>)}<text x="385" y="244">时间（分钟）</text>{rows.map((r,i)=><g key={r.id}><polyline points={points(r.q_pct)} stroke={colors[i]} fill="none" strokeWidth="1.5"/>{r.q_pct.map((v,j)=><circle key={j} cx={45+data.times[j]/30*410} cy={205-v*1.7} r="3" fill={colors[i]}/>)}</g>)}<polyline points={points(q)} stroke="#111" fill="none" strokeWidth="3" strokeDasharray="6 4"/></svg><p><strong>黑色粗虚线：当前滑块内插情景；彩色圆点：原始实测。</strong>端点处黑线与相应实测连线重合。</p><ul>{rows.map((r,i)=><li key={r.id}><span style={{color:colors[i]}}>━━ ● </span>{r.id}：淀粉{(r.starch_pct*.9).toFixed(3)} mg</li>)}</ul><p>当前内插：15 min {q[2].toFixed(2)}%；20 min {q[3].toFixed(2)}%；30 min {q[4].toFixed(2)}%。</p><p>Q(t)=(1−w)Q低(t)+wQ高(t)，w={w.toFixed(3)}；当前相邻实测为{low.id}/{high.id}。MCC30%系列保留中间F2，分段内插，不强制全时段单调。</p><p>与保存方案的区别：当前方案MCC29 mg、淀粉{trend.target.starch_after_mg} mg；滑块属于上面选定的实际研究系列，不能冒充当前方案的定量预测。{data.method}</p></section>;
}
