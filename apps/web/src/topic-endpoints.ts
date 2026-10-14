// Only the selected source case's saved calculations; never infer doses or pool conditions.
export function topicEndpoints(evidence:any[],run:any):any[]{
 const ids=new Set(run?.report?.interaction_research?.source_case?.calculation_ids??[]);
 return evidence.flatMap(e=>{
  if(!ids.has(e.id))return [];
  try{
   const r=JSON.parse(e.fields?.pair_difference_model_json??'null');
   if(!r?.pairs?.length||!r.unit)return [];
   if(!r.pairs.every((p:any)=>Number.isFinite(p.before)&&Number.isFinite(p.after)&&Number.isFinite(p.difference)&&Math.abs(p.after-p.before-p.difference)<1e-7))return [];
   return [{...r,id:e.id}];
  }catch{return []}
 });
}
