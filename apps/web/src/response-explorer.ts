export function responseValue(r:any,x:number):number|null {
 const m=r.models?.find((m:any)=>m.degree===r.selected_degree);
 if(!m || !Number.isFinite(x) || x<r.domain[0] || x>r.domain[1] || !(r.scale>0))return null;
 const z=(x-r.center)/r.scale;
 const y=m.coefficients.reduce((s:number,c:number,i:number)=>s+c*z**i,0);
 return Number.isFinite(y)?y:null;
}
export function responseGroups(evidence:any[],run:any):any[][] {
 const report=run?.report?.interaction_research;
 const ids=new Set([...(report?.source_case?.calculation_ids??[]),...(report?.studies??[]).flatMap((s:any)=>s.calculation_ids??[])]);
 const groups=new Map<string,any[]>();
 for(const e of evidence){
  if(!ids.has(e.id))continue;
  try{
   const r=JSON.parse(e.fields?.source_response_model_json??'null');
   if(!r||!r.observed?.length||!(r.domain[1]>r.domain[0])||responseValue(r,r.domain[0])===null)continue;
   // Reviewed F6–F9 record identities: same formulation series, distinct test methods.
   // Numerical values always come from the saved records, never from this mapping.
   const pandaSeries=['8723c933-4b90-4776-99b5-111783c7cb92','5369ea92-0a4a-4f1d-ae96-26f7be392b3c','2192eaa3-c87d-4a94-b970-e0f6f7325153','fdb6a6d1-6fa6-4a99-aa00-3ff7a023075b','4396042e-f2af-4fdd-a969-7a2ecd75bb70','340b3472-ab9a-4bc9-b79e-7cf02d72a74e'].includes(e.id)&&r.x_unit==='mg/tablet'&&JSON.stringify(r.domain)==='[10,30]';
   const key=pandaSeries?'reviewed-panda-F6-F9':JSON.stringify([r.source_id,r.conditions,r.x_name,r.x_unit,r.x_basis,r.domain]);
   const list=groups.get(key)??[];
   if(!list.some(v=>v.y_name===r.y_name&&v.y_unit===r.y_unit))list.push({...r,id:e.id,reviewedPandaSeries:pandaSeries});
   groups.set(key,list);
  }catch{/* Unreadable historical records remain in the archive. */}
 }
 return [...groups.values()];
}
