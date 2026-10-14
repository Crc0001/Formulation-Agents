import React from 'react';
import data from './known-release-validation.json';
export default function KnownReleaseValidation(){
 return <details><summary>已知案例复验：崩解变快，溶出是否一定跟着变快？</summary>
 <h3>左侧：来源数据与留出检查</h3><p>{data.identity}</p><p>{data.method}</p><p>{data.split}</p>
 <p>先用4%、8%估计“用量→崩解时间→达到80%溶出的时间t80”，再计算6%。公式：{data.equations.join('；')}。c为质量百分数数值。此为局部经验关系，用来检查三阶段建模假设，不是已完成三阶段机理验证。</p>
 <table><thead><tr><th>外加崩解剂（6%留出）</th><th>崩解：计算/原文（秒）</th><th>t80：计算/原文（分钟）</th><th>t80偏差（分钟）</th></tr></thead><tbody>{Object.entries(data.records).map(([k,r])=><tr key={k}><td>{r.name}<br/>{r.grade}</td><td>{r.holdout.pred_dt_s.toFixed(1)} / {r.dt_s[1]} ± {r.dt_sd_s[1]}</td><td>{r.holdout.pred_t80_min.toFixed(2)} / {r.t80_min[1]} ± {r.t80_sd_min[1]}</td><td>{r.holdout.error_min.toFixed(2)}</td></tr>)}</tbody></table>
 <p>以上±为原文SD，不是模型预测区间；单个留出处方不代表泛化已验证。</p>
 <svg viewBox="0 0 600 200" role="img" aria-label="三种崩解剂6%留出处方t80计算与实测对比">{Object.entries(data.records).map(([k,r],i)=><g key={k}><text x="5" y={30+i*58}>{k}</text><rect x="60" y={16+i*58} width={r.holdout.pred_t80_min*17} height="12" fill="#cc643c"/><rect x="60" y={31+i*58} width={r.holdout.observed_t80_min*17} height="12" fill="#087e8b"/><text x="480" y={33+i*58}>{r.holdout.pred_t80_min.toFixed(2)} / {r.holdout.observed_t80_min} min</text></g>)}</svg><p>橙：留出计算；蓝：原文实测均值。图为t80终点，不是完整溶出曲线。</p>
 <p className="callout">边界检验：CPV总量仍为6%，但全部内加。即使输入已知崩解时间957秒，沿用外加关系仅算出t80={data.challenge.pred_t80_min.toFixed(2)}分钟；原文却为101±9.8分钟。说明原外加关系不能直接跨加入方式使用。</p>
 <h3>右侧：对诺氟沙星方案研究的用途</h3><p>可采用“先预测中间物性，再检验溶出”的流程。已核对的诺氟沙星案例采用干法制粒胶囊，且调整的是MCC/预胶化淀粉比例；来源为熔融制粒片剂、改变崩解剂比例，物料和工艺均不同，以上系数不能直接迁移到该方案。</p><p>下一组对照应固定API粒度、囊壳、制粒和润滑条件，记录MCC/预胶化淀粉实际补差；同时测内容物崩散、颗粒吸液及湿态粒径、溶出。以崩散观测约束第一阶段，以吸液和暴露面积约束第二阶段，再检查剩余的溶出误差。应按完整配方/批次留出，不能随机拆时间点。</p>
 <details><summary>原始数值、参数和适用限制</summary><table><thead><tr><th>物料</th><th>用量%</th><th>DT 秒±SD</th><th>t80 分钟±SD</th></tr></thead><tbody>{Object.entries(data.records).flatMap(([k,r])=>[4,6,8].map((c,i)=><tr key={k+c}><td>{k}</td><td>{c}</td><td>{r.dt_s[i]}±{r.dt_sd_s[i]}</td><td>{r.t80_min[i]}±{r.t80_sd_min[i]}</td></tr>))}</tbody></table>{Object.entries(data.records).map(([k,r])=><p key={k}>{k}：α={r.parameters.alpha.toFixed(5)}，β={r.parameters.beta_per_weight_pp.toFixed(5)}/质量百分点；a={r.parameters.a_min.toFixed(5)}分钟，b={r.parameters.b.toFixed(5)}。若已知6%实测DT，t80计算为{r.holdout.conditional_t80_from_measured_dt.toFixed(2)}分钟（仍非独立贡献）。</p>)}{data.limitations.map(x=><p key={x}>{x}</p>)}<pre>{JSON.stringify(data.composition_pct,null,2)}</pre></details>
 <p><a href={data.source_url} target="_blank" rel="noreferrer">Steffens &amp; Wagner 2021 原文</a> · 表I–III、VII与Dissolution结果段；CC BY 4.0。数值摘录及计算为本次改编。</p>
 </details>;
}
