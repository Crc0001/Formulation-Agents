import SourcePairContrasts from './SourcePairContrasts';
import React from 'react';
export default function SavedSourceMetrics({evidence}:{evidence:any[]}){
 const items=evidence.flatMap(e=>{try{const d=JSON.parse(e.fields?.source_metric_json??'null');return d?[{e,d}]:[]}catch{return []}});
 return <section><SourcePairContrasts evidence={evidence}/><h2>已保存的来源数值对照</h2><p>以下是程序已归档的计算或对照，不依赖最终报告是否生成成功。颗粒崩解、片剂崩解和溶出按原指标分别阅读。</p>{items.slice().reverse().map(({e,d})=><details key={e.id} open={/Szumilo/.test(d.title)}><summary>{d.title}</summary><p>条件：{d.conditions}</p><table><thead><tr><th>来源样品及组成</th><th>响应（{d.unit}）</th></tr></thead><tbody>{d.points?.map((p:any,i:number)=><tr key={i}><td>{p.label}</td><td>{p.value}</td></tr>)}</tbody></table><p>定位：{d.locator}；限制：{d.limitations}</p><p>计算记录：{e.id}；原文记录：{d.source_id}</p></details>)}</section>
}
