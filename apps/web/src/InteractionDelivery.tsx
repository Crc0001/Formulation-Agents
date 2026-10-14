import React from 'react';

export default function InteractionDelivery({evidence,run,onNext}:{evidence:any[];run:any;onNext:()=>void}){
 const report=run?.report?.interaction_research;
 if(!report)return null;
 const ids=new Set([...(report.source_case?.calculation_ids??[]),...(report.pair_synthesis?.calculation_ids??[]),...(report.studies??[]).flatMap((s:any)=>s.calculation_ids??[])]);
 const records=evidence.filter(e=>ids.has(e.id)).flatMap(e=>{
  try{
   const curves=JSON.parse(e.fields?.source_curve_model_json??'null');
   if(curves?.arms?.some((a:any)=>a.models?.length))return [{id:e.id,title:curves.title??'来源溶出曲线',kind:'曲线模型',description:[...new Set(curves.arms.flatMap((a:any)=>(a.models??[]).map((m:any)=>m.model==='weibull'?'Weibull':m.model==='lag_first_order'?'延迟一阶':m.model)))].join('、'),use:'在来源条件下复现时间—溶出关系，比较原始点、拟合曲线和残差。'}];
   const pair=JSON.parse(e.fields?.pair_difference_model_json??'null');
   if(pair?.pairs?.length)return [{id:e.id,title:pair.title??'来源端点对照',kind:'差值计算',description:'两组来源响应差值及相对变化',use:'比较已测两组的变化幅度；不等同于连续用量模型。'}];
   const response=JSON.parse(e.fields?.source_response_model_json??'null');
   if(response?.models?.length)return [{id:e.id,title:response.y_name??'来源响应模型',kind:'响应模型',description:response.equation??'已保存来源响应关系',use:'在该来源的因素范围内查看条件模拟，迁移需另行核对。'}];
   return [];
  }catch{return []}
 });
 return <aside style={{border:'2px solid #087e8b',background:'#effafa',padding:20,borderRadius:12,marginBottom:20}} aria-label="03交付04成果概览">
  <h2>03 → 04：本轮可用成果</h2>
  <p><strong>{records.length?`已保存 ${records.length} 项来源计算成果，可以进入04查看图示。`:'本轮尚无可读取的数值计算成果。'}</strong></p>
  <p>专题来源：{report.source_case?.name??'见本轮研究报告'}。以下按计算记录列示，记录数量不代表独立验证次数。</p>
  {records.length>0&&<table><thead><tr><th>成果</th><th>已有计算</th><th>在04可做什么</th></tr></thead><tbody>{records.map(r=><tr key={r.id}><td>{r.title}<br/>{r.kind}</td><td>{r.description}</td><td>{r.use}</td></tr>)}</tbody></table>}
  <p><strong>当前处方的应用范围：</strong>{report.source_case?.target_transfer??report.pair_synthesis?.comparability??'尚未交付目标迁移判断，请先核对来源条件。'}</p>
  <button onClick={onNext}>{records.length?'进入04，查看已有模型与曲线':'进入04，查看专题状态'}</button>
  <p>点击只切换工作台，不启动研究、不重新计算。04顶部按辅料专题读取已保存成果；没有用量映射时，不能通过调整当前处方直接生成预测。</p>
 </aside>;
}
