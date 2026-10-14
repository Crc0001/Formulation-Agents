import React from 'react';
export default function SourceDoeHandoff({records,baselineId}:{records:any[];baselineId:string}){
 const rows=records.filter(r=>r.baseline_id===baselineId);
 return <section><h2>03交付的来源DoE验证包</h2><p>这是来源药物的用量留出验证入口，与当前项目处方编辑分开。无需先调整当前处方。</p>{!rows.length&&<p>到03来源模型结果中点击“交给04：V60来源用量留出验证”，即可传入。</p>}{rows.slice().reverse().map(r=><article key={r.id}><h3>{r.factor}：5%和10%建模，7.5%留出</h3><p>状态：接口交接完成，留出预测尚未执行。</p><p>训练数据：{r.training.map((a:any)=>`${a.level}%（${a.points.length}点）`).join('、')}。7.5%的{r.heldout_point_count}个响应点单独封存，不放入此训练包。</p><p>预定方法：延迟一阶；两端重新拟合，再按用量线性插值参数。先保存预测版本，再比较7.5%来源曲线。</p><p>交接记录：{r.id}；来源模型：{r.source_model_id}。</p>{r.limitations.map((s:string)=><p key={s}>{s}</p>)}</article>)}</section>
}
