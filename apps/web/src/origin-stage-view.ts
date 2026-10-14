export function originRunStage(message:string):number|null {
 message=message.replace(/^(?:【外部成果导入；原始运行 [^】]+】)+/,'');
 const m=message.match(/^(?:【原研及处方工艺】)?(?:【接续：汇总】)?\s*(?:【01阶段([123])】|第([一二三])阶段[:： ·])/);
 return m?(m[1]?Number(m[1]):({'一':1,'二':2,'三':3} as any)[m[2]]):null;
}
export function stageRun(runs:any[],stage:number){
 const newest=[...runs].reverse().filter(r=>r.report);
 const useful=(r:any)=>stage===1?!!r.report.decision_comparison?.rows?.some((x:any)=>x.metric==='说明书辅料组成'):(stage===2?!!r.report.formulations?.length:!!r.report.origin_recommendation);
 // Explicit stage outputs take precedence over incidental rows in another stage.
 return newest.find(r=>originRunStage(r.message??'')===stage)
  ??newest.find(r=>originRunStage(r.message??'')===null&&useful(r));
}
export function uniqueOriginCandidates(runs:any[]){
 const seen=new Set<string>();const out:any[]=[];
 for(const run of [...runs].reverse())for(const f of run.report?.formulations??[]){
  const key=JSON.stringify([f,run.report.processes??[],run.report.dissolution_curves??[]]);
  if(seen.has(key))continue;seen.add(key);out.push({formula:f,report:run.report,runId:run.id});
 }
 return out;
}
