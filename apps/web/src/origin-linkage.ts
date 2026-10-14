function identity(text:string){
 const patents=[...text.toUpperCase().matchAll(/\b(?:CN|WO|US|EP|JP)\s*\d{6,}[A-Z]\d?\b/g)].map(m=>m[0].replace(/\s/g,''));
 const examples=[...text.matchAll(/(?:对比实施例|对照实施例|比较实施例|实施例|对比例|对照例)\s*\d+(?!\d)/g)].map(m=>m[0].replace(/\s/g,''));
 return patents.length===1&&examples.length===1?patents[0]+'|'+examples[0]:null;
}
export function matchingProcesses(formula:any,report:any){
 const fid=identity(formula.title??'');
 return (report.processes??[]).filter((p:any)=>{
  if(!(p.source_ids??[]).some((id:string)=>(formula.source_ids??[]).includes(id)))return false;
  if(p.scope===formula.title||p.title===formula.title||p.title===formula.title+'工艺')return true;
  // Exact patent and example identities, never a substring such as example 1 in 10.
  return fid!==null&&fid===identity(p.scope||p.title||'');
 });
}
export function originChecklist(f:any,r:any,requireDissolution=true){
 const processes=matchingProcesses(f,r);
 const curves=(r.dissolution_curves??[]).filter((c:any)=>c.formula_title===f.title&&(c.source_ids??[]).some((id:string)=>(f.source_ids??[]).includes(id)));
 const issues:string[]=[];
 if(!processes.length)issues.push('候选对应的结构化工艺尚未关联；推荐文字不自动当作原文工艺。');
 if(requireDissolution&&!curves.length)issues.push('尚无已结构化关联的候选自身溶出曲线；不能借用原研对照或其它实施例。');
 const components=f.components??[];
 if(components.some((c:any)=>c.amount_mg==null))issues.push('部分单单位用量未明确；需保留批量/比例及换算依据。');
 if(components.some((c:any)=>c.batch_amount!=null)&&!f.batch_units)issues.push('有批量列量但结构化批量单位数缺失，暂不能逐项核算批量与单片量。');
 for(const c of components){
  const factor=({mg:1,g:1000,kg:1e6} as any)[c.batch_mass_unit];
  if(f.batch_units>0&&c.batch_amount!=null&&c.amount_mg!=null&&factor){
   const single=c.batch_amount*factor/f.batch_units;
   if(Math.abs(single-c.amount_mg)>Math.max(.001,Math.abs(c.amount_mg)*.001))issues.push(`${c.name}：批量折算${Number(single.toFixed(6))} mg与列示${c.amount_mg} mg不一致，保留两值待核。`);
  }
 }
 return {processes,curves,issues};
}
