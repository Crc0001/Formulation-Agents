// Local source calibration is deliberately separate from target transfer assumptions.
export function fitLine(points: number[][]) {
 if(points.length<3||points.some(p=>p.length!==2||!p.every(Number.isFinite)))throw Error('至少三个有限数值来源点');
 const n=points.length,mx=points.reduce((s,p)=>s+p[0],0)/n,my=points.reduce((s,p)=>s+p[1],0)/n;
 const xx=points.reduce((s,p)=>s+(p[0]-mx)**2,0);if(xx===0)throw Error('来源横坐标无变化');
 const slope=points.reduce((s,p)=>s+(p[0]-mx)*(p[1]-my),0)/xx,intercept=my-slope*mx;
 const fitted=points.map(p=>intercept+slope*p[0]),residuals=points.map((p,i)=>p[1]-fitted[i]);
 return {slope,intercept,fitted,residuals,rmse:Math.sqrt(residuals.reduce((s,r)=>s+r*r,0)/n),domain:[Math.min(...points.map(p=>p[0])),Math.max(...points.map(p=>p[0]))]};
}
export function fraction(items:any[],id:string){
 if(!items?.length||items.some(x=>!Number.isFinite(x.amount_mg)||x.amount_mg<0))throw Error('物料质量未知');
 const total=items.reduce((s,x)=>s+x.amount_mg,0),item=items.find(x=>x.id===id);
 if(!item||total<=0)throw Error('物料或总量未知');return 100*item.amount_mg/total;
}
export function transferDelta(slope:number,before:number,after:number,eta:number){
 if(![slope,before,after,eta].every(Number.isFinite)||before<0||after<0||before>100||after>100)throw Error('迁移坐标非法');
 return 100*eta*slope*(after-before); // porosity percentage points, not dissolution
}
export function runVariant(run:any){try{return JSON.parse(run?.message?.split('\n变化方案：')[1]?.split('\n问题：')[0]??'null')?.id??null}catch{return null}}
export function sourceMetrics(evidence:any[]){
 const unique=new Map<string,any>();
 for(const e of evidence){try{const m=JSON.parse(e.fields?.source_metric_json??'null'),source=evidence.find(s=>s.id===m?.source_id);
 if(!m||!source||!Array.isArray(m.points)||m.points.length<2||!m.points.every((p:any)=>Number.isFinite(p.value)))continue;
 // Same source, metric, conditions and values only. Different conditions stay separate.
 const key=JSON.stringify([source.source_url,m.quantity,m.unit,m.conditions,m.points]);
 unique.set(key,{metric:m,source,id:e.id});}catch{}}
 return [...unique.values()];
}
